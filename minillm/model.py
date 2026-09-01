from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Optional, Sequence

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from .config import ModelConfig


@dataclass
class CausalLMOutput:
    loss: Optional[Tensor]
    logits: Tensor
    past_key_values: Optional[tuple[tuple[Tensor, Tensor], ...]] = None


class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-5) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.ones(dim))
        self.eps = eps

    def forward(self, x: Tensor) -> Tensor:
        # Computing the statistic in float32 is more stable for fp16/bf16.
        normed = x.float() * torch.rsqrt(x.float().pow(2).mean(dim=-1, keepdim=True) + self.eps)
        return (self.weight * normed).to(dtype=x.dtype)


def _rotate_half(x: Tensor) -> Tensor:
    half = x.shape[-1] // 2
    return torch.cat((-x[..., half:], x[..., :half]), dim=-1)


def _apply_rope(q: Tensor, k: Tensor, cos: Tensor, sin: Tensor) -> tuple[Tensor, Tensor]:
    # q/k: [batch, heads, sequence, head_dim]
    cos = cos[None, None, :, :]
    sin = sin[None, None, :, :]
    return q * cos + _rotate_half(q) * sin, k * cos + _rotate_half(k) * sin


def _repeat_kv(x: Tensor, repeats: int) -> Tensor:
    """Expand grouped-query K/V heads without allocating until necessary."""

    if repeats == 1:
        return x
    batch, heads, sequence, head_dim = x.shape
    return (
        x[:, :, None, :, :]
        .expand(batch, heads, repeats, sequence, head_dim)
        .reshape(batch, heads * repeats, sequence, head_dim)
    )


def _build_rope_cache(
    max_seq_len: int, head_dim: int, theta: float, device: torch.device | None = None
) -> tuple[Tensor, Tensor]:
    if head_dim % 2:
        raise ValueError("head_dim must be even for rotary embeddings")
    positions = torch.arange(max_seq_len, dtype=torch.float32, device=device)
    inverse_frequency = 1.0 / (
        theta ** (torch.arange(0, head_dim, 2, dtype=torch.float32, device=device) / head_dim)
    )
    frequencies = torch.outer(positions, inverse_frequency)
    # Interleaving is not required when rotate_half uses the same duplicated
    # halves; this is the layout used by the reference MiniMind implementation.
    cos = torch.cat((frequencies.cos(), frequencies.cos()), dim=-1)
    sin = torch.cat((frequencies.sin(), frequencies.sin()), dim=-1)
    return cos, sin


class CausalSelfAttention(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.n_heads = config.n_heads
        self.n_kv_heads = config.n_kv_heads
        self.kv_repeats = config.n_heads // config.n_kv_heads
        self.head_dim = config.head_dim
        self.dropout = config.dropout

        self.q_proj = nn.Linear(config.dim, config.n_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(config.dim, config.n_kv_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(config.dim, config.n_kv_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(config.n_heads * self.head_dim, config.dim, bias=False)
        self.q_norm = RMSNorm(self.head_dim, eps=config.rms_norm_eps)
        self.k_norm = RMSNorm(self.head_dim, eps=config.rms_norm_eps)
        self.resid_dropout = nn.Dropout(config.dropout)

    def forward(
        self,
        x: Tensor,
        cos: Tensor,
        sin: Tensor,
        start_pos: int = 0,
        past_key_value: Optional[tuple[Tensor, Tensor]] = None,
        use_cache: bool = False,
        attention_mask: Optional[Tensor] = None,
    ) -> tuple[Tensor, Optional[tuple[Tensor, Tensor]]]:
        batch, sequence, _ = x.shape
        q = self.q_proj(x).view(batch, sequence, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(batch, sequence, self.n_kv_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(batch, sequence, self.n_kv_heads, self.head_dim).transpose(1, 2)
        q = self.q_norm(q)
        k = self.k_norm(k)
        q, k = _apply_rope(
            q,
            k,
            cos[start_pos : start_pos + sequence],
            sin[start_pos : start_pos + sequence],
        )

        past_length = 0
        if past_key_value is not None:
            past_k, past_v = past_key_value
            past_length = past_k.shape[2]
            k = torch.cat((past_k, k), dim=2)
            v = torch.cat((past_v, v), dim=2)
        present = (k, v) if use_cache else None

        q_len = q.shape[2]
        k_len = k.shape[2]
        k_for_attention = _repeat_kv(k, self.kv_repeats)
        v_for_attention = _repeat_kv(v, self.kv_repeats)

        # The fused PyTorch attention path is both faster and less memory hungry
        # when it is available.  A boolean mask uses True for positions that
        # are allowed to attend.
        if past_length == 0 and attention_mask is None:
            output = F.scaled_dot_product_attention(
                q,
                k_for_attention,
                v_for_attention,
                dropout_p=self.dropout if self.training else 0.0,
                is_causal=True,
            )
        else:
            query_positions = torch.arange(
                start_pos, start_pos + q_len, device=x.device
            )
            key_positions = torch.arange(k_len, device=x.device)
            allowed = key_positions[None, :] <= query_positions[:, None]
            allowed = allowed[None, None, :, :]
            if attention_mask is not None:
                if attention_mask.shape[-1] != k_len:
                    raise ValueError(
                        "attention_mask must cover the complete cached key sequence "
                        f"({attention_mask.shape[-1]} != {k_len})"
                    )
                allowed = allowed & attention_mask[:, None, None, :].bool()
            output = F.scaled_dot_product_attention(
                q,
                k_for_attention,
                v_for_attention,
                attn_mask=allowed,
                dropout_p=self.dropout if self.training else 0.0,
                is_causal=False,
            )

        output = output.transpose(1, 2).contiguous().view(batch, sequence, -1)
        return self.resid_dropout(self.o_proj(output)), present


class SwiGLU(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        hidden = int(config.intermediate_size)
        self.gate_proj = nn.Linear(config.dim, hidden, bias=False)
        self.up_proj = nn.Linear(config.dim, hidden, bias=False)
        self.down_proj = nn.Linear(hidden, config.dim, bias=False)

    def forward(self, x: Tensor) -> Tensor:
        return self.down_proj(F.silu(self.gate_proj(x)) * self.up_proj(x))


class TransformerBlock(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.input_norm = RMSNorm(config.dim, eps=config.rms_norm_eps)
        self.attention = CausalSelfAttention(config)
        self.post_attention_norm = RMSNorm(config.dim, eps=config.rms_norm_eps)
        self.feed_forward = SwiGLU(config)

    def forward(
        self,
        x: Tensor,
        cos: Tensor,
        sin: Tensor,
        start_pos: int,
        past_key_value: Optional[tuple[Tensor, Tensor]],
        use_cache: bool,
        attention_mask: Optional[Tensor],
    ) -> tuple[Tensor, Optional[tuple[Tensor, Tensor]]]:
        attention_output, present = self.attention(
            self.input_norm(x),
            cos,
            sin,
            start_pos=start_pos,
            past_key_value=past_key_value,
            use_cache=use_cache,
            attention_mask=attention_mask,
        )
        x = x + attention_output
        x = x + self.feed_forward(self.post_attention_norm(x))
        return x, present


class TinyCausalLM(nn.Module):
    """A small decoder-only Transformer with a MiniMind-like interface."""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.config = config
        self.embed_tokens = nn.Embedding(config.vocab_size, config.dim)
        self.embedding_dropout = nn.Dropout(config.dropout)
        self.layers = nn.ModuleList(
            [TransformerBlock(config) for _ in range(config.n_layers)]
        )
        self.final_norm = RMSNorm(config.dim, eps=config.rms_norm_eps)
        self.lm_head = nn.Linear(config.dim, config.vocab_size, bias=False)
        if config.tie_embeddings:
            self.lm_head.weight = self.embed_tokens.weight

        cos, sin = _build_rope_cache(
            config.max_seq_len, config.head_dim, config.rope_theta
        )
        self.register_buffer("rope_cos", cos, persistent=False)
        self.register_buffer("rope_sin", sin, persistent=False)
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
        elif isinstance(module, RMSNorm):
            nn.init.ones_(module.weight)

    def num_parameters(self, trainable_only: bool = True) -> int:
        parameters: Iterable[Tensor] = self.parameters()
        if trainable_only:
            parameters = (parameter for parameter in parameters if parameter.requires_grad)
        return sum(parameter.numel() for parameter in parameters)

    def forward(
        self,
        input_ids: Tensor,
        labels: Optional[Tensor] = None,
        attention_mask: Optional[Tensor] = None,
        past_key_values: Optional[Sequence[Optional[tuple[Tensor, Tensor]]]] = None,
        use_cache: bool = False,
        logits_to_keep: Optional[int] = None,
    ) -> CausalLMOutput:
        if input_ids.ndim != 2:
            raise ValueError("input_ids must have shape [batch, sequence]")
        batch, sequence = input_ids.shape
        if sequence == 0:
            raise ValueError("input_ids cannot be empty")

        if past_key_values is None:
            past_key_values = [None] * len(self.layers)
        elif len(past_key_values) != len(self.layers):
            raise ValueError("past_key_values must contain one entry per layer")

        past_length = 0
        if past_key_values[0] is not None:
            past_length = past_key_values[0][0].shape[2]
        if past_length + sequence > self.config.max_seq_len:
            raise ValueError(
                f"sequence exceeds max_seq_len={self.config.max_seq_len}: "
                f"past={past_length}, new={sequence}"
            )

        x = self.embedding_dropout(self.embed_tokens(input_ids))
        cos = self.rope_cos.to(device=x.device, dtype=x.dtype)
        sin = self.rope_sin.to(device=x.device, dtype=x.dtype)
        presents: list[Optional[tuple[Tensor, Tensor]]] = []
        for layer, past in zip(self.layers, past_key_values):
            x, present = layer(
                x,
                cos,
                sin,
                start_pos=past_length,
                past_key_value=past,
                use_cache=use_cache,
                attention_mask=attention_mask,
            )
            presents.append(present)

        hidden = self.final_norm(x)
        if logits_to_keep is not None:
            if logits_to_keep <= 0:
                raise ValueError("logits_to_keep must be positive")
            hidden_for_logits = hidden[:, -logits_to_keep:]
        else:
            hidden_for_logits = hidden
        logits = self.lm_head(hidden_for_logits)

        loss: Optional[Tensor] = None
        if labels is not None:
            if labels.shape != input_ids.shape:
                raise ValueError("labels must have the same shape as input_ids")
            if logits_to_keep is not None:
                labels = labels[:, -logits_to_keep:]
            if logits.shape[1] < 2:
                raise ValueError("at least two tokens are required to compute loss")
            loss = F.cross_entropy(
                logits[:, :-1].contiguous().view(-1, logits.shape[-1]),
                labels[:, 1:].contiguous().view(-1),
                ignore_index=-100,
            )

        # None entries only occur when use_cache=False; type narrowing is not
        # important to callers, while a tuple is convenient for generation.
        cached = tuple(presents) if use_cache else None
        return CausalLMOutput(loss=loss, logits=logits, past_key_values=cached)  # type: ignore[arg-type]

    @staticmethod
    def _sample_next_token(
        logits: Tensor, temperature: float, top_k: int, top_p: float
    ) -> Tensor:
        if temperature <= 0:
            return torch.argmax(logits, dim=-1, keepdim=True)
        logits = logits / temperature
        if top_k > 0:
            top_k = min(top_k, logits.shape[-1])
            threshold = torch.topk(logits, top_k, dim=-1).values[..., -1, None]
            logits = logits.masked_fill(logits < threshold, float("-inf"))
        if 0 < top_p < 1.0:
            sorted_logits, sorted_indices = torch.sort(logits, descending=True, dim=-1)
            cumulative = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
            remove = cumulative > top_p
            remove[..., 1:] = remove[..., :-1].clone()
            remove[..., 0] = False
            sorted_logits = sorted_logits.masked_fill(remove, float("-inf"))
            logits = torch.full_like(logits, float("-inf")).scatter(
                -1, sorted_indices, sorted_logits
            )
        probabilities = F.softmax(logits, dim=-1)
        return torch.multinomial(probabilities, num_samples=1)

    @torch.no_grad()
    def generate(
        self,
        input_ids: Tensor,
        max_new_tokens: int = 64,
        temperature: float = 0.8,
        top_k: int = 50,
        top_p: float = 0.9,
        eos_token_id: Optional[int] = None,
    ) -> Tensor:
        """Generate tokens using KV cache, resetting the cache at context limit."""

        if input_ids.ndim != 2:
            raise ValueError("input_ids must have shape [batch, sequence]")
        if max_new_tokens < 0:
            raise ValueError("max_new_tokens cannot be negative")
        self.eval()
        generated = input_ids[:, -self.config.max_seq_len :].clone()
        past: Optional[tuple[tuple[Tensor, Tensor], ...]] = None
        finished = torch.zeros(generated.shape[0], dtype=torch.bool, device=generated.device)
        eos_token_id = self.config.eos_token_id if eos_token_id is None else eos_token_id

        for _ in range(max_new_tokens):
            if past is not None and past[0][0].shape[2] >= self.config.max_seq_len:
                # Keep generation usable beyond the fixed context window.  We
                # lose the old cache, but retain the most recent context.
                generated = generated[:, -self.config.max_seq_len :]
                past = None
            model_input = generated if past is None else generated[:, -1:]
            output = self(
                model_input,
                past_key_values=past,
                use_cache=True,
            )
            next_token = self._sample_next_token(
                output.logits[:, -1, :], temperature=temperature, top_k=top_k, top_p=top_p
            )
            if eos_token_id is not None:
                replacement = torch.full_like(next_token, eos_token_id)
                next_token = torch.where(finished[:, None], replacement, next_token)
            generated = torch.cat((generated, next_token), dim=1)
            past = output.past_key_values
            if eos_token_id is not None:
                finished |= next_token.squeeze(-1).eq(eos_token_id)
                if bool(finished.all()):
                    break
        return generated
