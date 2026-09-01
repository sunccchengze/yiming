from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path
from typing import Any


@dataclass
class ModelConfig:
    """Configuration for the decoder-only language model.

    The defaults intentionally describe a tiny CPU-friendly model.  The JSON
    presets in ``configs/`` scale the same implementation up without changing
    the training code.
    """

    vocab_size: int = 256
    max_seq_len: int = 128
    dim: int = 96
    n_layers: int = 3
    n_heads: int = 3
    n_kv_heads: int = 3
    intermediate_size: int | None = 256
    dropout: float = 0.0
    rope_theta: float = 10000.0
    rms_norm_eps: float = 1e-5
    tie_embeddings: bool = True
    bos_token_id: int = 1
    eos_token_id: int = 2
    pad_token_id: int = 0

    def __post_init__(self) -> None:
        if self.dim <= 0 or self.n_layers <= 0:
            raise ValueError("dim and n_layers must be positive")
        if self.n_heads <= 0 or self.dim % self.n_heads != 0:
            raise ValueError("dim must be divisible by n_heads")
        if self.n_kv_heads <= 0 or self.n_heads % self.n_kv_heads != 0:
            raise ValueError("n_heads must be divisible by n_kv_heads")
        if self.max_seq_len <= 0 or self.vocab_size <= 0:
            raise ValueError("max_seq_len and vocab_size must be positive")
        if self.intermediate_size is None:
            # SwiGLU has three projections; this is a common parameter-sized
            # equivalent to a four-times ReLU/SwiGLU feed-forward layer.
            self.intermediate_size = ((8 * self.dim // 3 + 63) // 64) * 64
        if self.intermediate_size <= 0:
            raise ValueError("intermediate_size must be positive")

    @property
    def head_dim(self) -> int:
        return self.dim // self.n_heads

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "ModelConfig":
        allowed = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in values.items() if key in allowed})

    @classmethod
    def from_json(cls, path: str | Path) -> "ModelConfig":
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def save_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
