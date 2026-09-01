from __future__ import annotations

import argparse
from pathlib import Path

import torch

from .config import ModelConfig
from .data import format_prompt
from .model import TinyCausalLM
from .tokenizer import CharTokenizer


def load_model(checkpoint_path: str | Path, device: torch.device) -> TinyCausalLM:
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    if "config" not in checkpoint or "model" not in checkpoint:
        raise ValueError("checkpoint must contain config and model entries")
    config = ModelConfig.from_dict(checkpoint["config"])
    model = TinyCausalLM(config)
    model.load_state_dict(checkpoint["model"])
    return model.to(device).eval()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate text from a trained checkpoint")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    device = torch.device(args.device)
    tokenizer = CharTokenizer.load(args.tokenizer)
    model = load_model(args.checkpoint, device)
    input_ids = torch.tensor(
        [format_prompt(args.prompt, tokenizer)], dtype=torch.long, device=device
    )
    generated = model.generate(
        input_ids,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_k=args.top_k,
        top_p=args.top_p,
    )
    print(tokenizer.decode(generated[0].tolist()))


if __name__ == "__main__":
    main()
