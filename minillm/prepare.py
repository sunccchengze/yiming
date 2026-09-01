from __future__ import annotations

import argparse
from pathlib import Path

from .tokenizer import CharTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the first-stage character tokenizer")
    parser.add_argument("--pretrain", nargs="+", required=True, help="pretraining JSONL files")
    parser.add_argument("--sft", nargs="*", default=[], help="optional SFT JSONL files")
    parser.add_argument("--vocab-size", type=int, default=2048)
    parser.add_argument("--out", required=True, help="output tokenizer JSON path")
    args = parser.parse_args()

    paths = [Path(path) for path in [*args.pretrain, *args.sft]]
    tokenizer = CharTokenizer.from_jsonl(paths, vocab_size=args.vocab_size)
    tokenizer.save(args.out)
    print(f"tokenizer saved to {args.out}")
    print(f"vocab_size={tokenizer.vocab_size}")
    print(
        "special_tokens="
        f"bos:{tokenizer.bos_token_id} "
        f"eos:{tokenizer.eos_token_id} "
        f"pad:{tokenizer.pad_token_id} "
        f"unk:{tokenizer.unk_token_id}"
    )


if __name__ == "__main__":
    main()
