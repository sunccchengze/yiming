from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Iterable, Iterator


SPECIAL_TOKENS = ("<pad>", "<bos>", "<eos>", "<unk>")


class CharTokenizer:
    """A deterministic character tokenizer for the first training milestone.

    MiniMind uses a more capable BPE/ByteLevel tokenizer in its main line.  A
    character vocabulary keeps this first implementation dependency-light and
    makes every tokenization decision easy to inspect.  The model interface is
    intentionally tokenizer-agnostic, so a BPE tokenizer can replace this one
    in a later milestone.
    """

    format_version = 1

    def __init__(self, tokens: list[str]):
        if len(tokens) < len(SPECIAL_TOKENS):
            raise ValueError("the vocabulary is missing special tokens")
        if tuple(tokens[: len(SPECIAL_TOKENS)]) != SPECIAL_TOKENS:
            raise ValueError(
                "the first vocabulary entries must be " + repr(SPECIAL_TOKENS)
            )
        if len(set(tokens)) != len(tokens):
            raise ValueError("the vocabulary contains duplicate tokens")
        self.tokens = list(tokens)
        self._token_to_id = {token: index for index, token in enumerate(tokens)}

        self.pad_token_id = self._token_to_id["<pad>"]
        self.bos_token_id = self._token_to_id["<bos>"]
        self.eos_token_id = self._token_to_id["<eos>"]
        self.unk_token_id = self._token_to_id["<unk>"]

    @property
    def vocab_size(self) -> int:
        return len(self.tokens)

    @classmethod
    def build(cls, texts: Iterable[str], vocab_size: int = 2048) -> "CharTokenizer":
        if vocab_size < len(SPECIAL_TOKENS):
            raise ValueError("vocab_size is smaller than the special-token count")

        counts: Counter[str] = Counter()
        for text in texts:
            counts.update(str(text))

        # Frequency first gives small, useful vocabularies; the lexical tie
        # break makes the generated tokenizer reproducible across runs.
        characters = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        tokens = list(SPECIAL_TOKENS)
        for character, _ in characters:
            if character not in tokens:
                tokens.append(character)
            if len(tokens) >= vocab_size:
                break
        return cls(tokens)

    @classmethod
    def from_jsonl(
        cls, paths: Iterable[str | Path], vocab_size: int = 2048
    ) -> "CharTokenizer":
        return cls.build(iter_jsonl_texts(paths), vocab_size=vocab_size)

    def encode(
        self, text: str, *, add_bos: bool = False, add_eos: bool = False
    ) -> list[int]:
        ids: list[int] = []
        if add_bos:
            ids.append(self.bos_token_id)
        ids.extend(self._token_to_id.get(character, self.unk_token_id) for character in text)
        if add_eos:
            ids.append(self.eos_token_id)
        return ids

    def decode(self, ids: Iterable[int], *, skip_special_tokens: bool = True) -> str:
        pieces: list[str] = []
        for raw_id in ids:
            index = int(raw_id)
            if index < 0 or index >= len(self.tokens):
                token = "<unk>"
            else:
                token = self.tokens[index]
            if skip_special_tokens and token in SPECIAL_TOKENS:
                continue
            pieces.append(token)
        return "".join(pieces)

    def token_to_id(self, token: str) -> int:
        return self._token_to_id.get(token, self.unk_token_id)

    def id_to_token(self, index: int) -> str:
        return self.tokens[int(index)]

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format_version": self.format_version,
            "type": "char",
            "tokens": self.tokens,
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    @classmethod
    def load(cls, path: str | Path) -> "CharTokenizer":
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("type") != "char":
            raise ValueError("this loader only understands a char tokenizer")
        return cls(list(payload["tokens"]))


def read_jsonl(path: str | Path) -> Iterator[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on {path}:{line_number}") from error
            if not isinstance(value, dict):
                raise ValueError(f"expected an object on {path}:{line_number}")
            yield value


def iter_jsonl_texts(paths: Iterable[str | Path]) -> Iterator[str]:
    """Yield text from both pretraining and chat JSONL formats."""

    for path in paths:
        for record in read_jsonl(path):
            text = record.get("text")
            if text is not None:
                yield str(text)

            conversations = record.get("conversations")
            if isinstance(conversations, list):
                for message in conversations:
                    if isinstance(message, dict) and message.get("content") is not None:
                        yield str(message["content"])
