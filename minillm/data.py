from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

import torch
from torch import Tensor
from torch.utils.data import Dataset

from .tokenizer import CharTokenizer, read_jsonl


def _pad_example(
    input_ids: list[int], labels: list[int], max_seq_len: int, pad_token_id: int
) -> tuple[Tensor, Tensor, Tensor]:
    # Keep one extra token while constructing examples, then use the first
    # max_seq_len positions as model input and the next position as target.
    input_ids = input_ids[:max_seq_len]
    labels = labels[:max_seq_len]
    padding = max_seq_len - len(input_ids)
    if padding > 0:
        input_ids = input_ids + [pad_token_id] * padding
        labels = labels + [-100] * padding
    attention_mask = [1 if token != pad_token_id else 0 for token in input_ids]
    return (
        torch.tensor(input_ids, dtype=torch.long),
        torch.tensor(labels, dtype=torch.long),
        torch.tensor(attention_mask, dtype=torch.long),
    )


class PretrainDataset(Dataset[dict[str, Tensor]]):
    """Next-token examples built from JSONL records containing ``text``."""

    def __init__(
        self,
        path: str | Path,
        tokenizer: CharTokenizer,
        max_seq_len: int,
    ) -> None:
        if max_seq_len < 2:
            raise ValueError("max_seq_len must be at least 2")
        all_tokens: list[int] = []
        for record in read_jsonl(path):
            text = record.get("text")
            if text is None:
                continue
            all_tokens.extend(tokenizer.encode(str(text), add_bos=True, add_eos=True))

        if len(all_tokens) < 2:
            raise ValueError(f"pretraining file has no usable text: {path}")
        self.examples: list[dict[str, Tensor]] = []
        # A stride equal to the block size prevents accidental duplicate-heavy
        # samples while retaining every document boundary token.
        for start in range(0, max(1, len(all_tokens) - 1), max_seq_len):
            chunk = all_tokens[start : start + max_seq_len + 1]
            if len(chunk) < 2:
                continue
            input_ids = chunk[:-1]
            labels = chunk[1:]
            input_tensor, label_tensor, mask_tensor = _pad_example(
                input_ids, labels, max_seq_len, tokenizer.pad_token_id
            )
            self.examples.append(
                {
                    "input_ids": input_tensor,
                    "labels": label_tensor,
                    "attention_mask": mask_tensor,
                }
            )
        if not self.examples:
            raise ValueError(f"pretraining file did not produce any examples: {path}")

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, Tensor]:
        return self.examples[index]


_ROLE_PREFIX = {
    "system": "系统：",
    "user": "用户：",
    "assistant": "助手：",
}


def _chat_example(
    conversations: list[dict], tokenizer: CharTokenizer, max_seq_len: int
) -> tuple[Tensor, Tensor, Tensor]:
    input_ids = [tokenizer.bos_token_id]
    labels = [-100]
    last_assistant = False
    for message in conversations:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "user")).lower()
        role = role if role in _ROLE_PREFIX else "user"
        content = str(message.get("content", ""))
        prefix_ids = tokenizer.encode(_ROLE_PREFIX[role])
        content_ids = tokenizer.encode(content)
        newline_ids = tokenizer.encode("\n")
        input_ids.extend(prefix_ids)
        labels.extend([-100] * len(prefix_ids))
        input_ids.extend(content_ids)
        if role == "assistant":
            labels.extend(content_ids)
            last_assistant = True
        else:
            labels.extend([-100] * len(content_ids))
            last_assistant = False
        input_ids.extend(newline_ids)
        labels.extend(newline_ids if role == "assistant" else [-100] * len(newline_ids))

    input_ids.append(tokenizer.eos_token_id)
    labels.append(tokenizer.eos_token_id if last_assistant else -100)
    return _pad_example(input_ids, labels, max_seq_len, tokenizer.pad_token_id)


class SFTDataset(Dataset[dict[str, Tensor]]):
    """Instruction-tuning examples with loss applied only to assistant turns."""

    def __init__(
        self,
        path: str | Path,
        tokenizer: CharTokenizer,
        max_seq_len: int,
    ) -> None:
        self.examples: list[dict[str, Tensor]] = []
        for record in read_jsonl(path):
            conversations = record.get("conversations")
            if not isinstance(conversations, list):
                continue
            input_ids, labels, attention_mask = _chat_example(
                conversations, tokenizer, max_seq_len
            )
            if bool((labels != -100).any()):
                self.examples.append(
                    {
                        "input_ids": input_ids,
                        "labels": labels,
                        "attention_mask": attention_mask,
                    }
                )
        if not self.examples:
            raise ValueError(f"SFT file has no usable assistant responses: {path}")

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, Tensor]:
        return self.examples[index]


def format_prompt(prompt: str, tokenizer: CharTokenizer) -> list[int]:
    """Format a one-turn prompt in the same style used by SFTDataset."""

    text = f"用户：{prompt}\n助手："
    return tokenizer.encode(text, add_bos=True)


def count_non_padding_tokens(dataset: Dataset[dict[str, Tensor]]) -> int:
    return sum(int(example["attention_mask"].sum()) for example in dataset)
