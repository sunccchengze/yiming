from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import math
from pathlib import Path
import random
import time
from typing import Iterator

import torch
from torch import Tensor
from torch.utils.data import DataLoader, Dataset

from .config import ModelConfig
from .data import PretrainDataset, SFTDataset
from .model import TinyCausalLM
from .tokenizer import CharTokenizer


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def iter_forever(loader: DataLoader[dict[str, Tensor]]) -> Iterator[dict[str, Tensor]]:
    while True:
        for batch in loader:
            yield batch


def learning_rate_at(
    step: int, max_steps: int, base_lr: float, warmup_steps: int, min_ratio: float
) -> float:
    if warmup_steps > 0 and step <= warmup_steps:
        return base_lr * step / warmup_steps
    progress = (step - warmup_steps) / max(1, max_steps - warmup_steps)
    progress = min(1.0, max(0.0, progress))
    cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
    return base_lr * (min_ratio + (1.0 - min_ratio) * cosine)


def save_checkpoint(
    path: Path,
    model: TinyCausalLM,
    optimizer: torch.optim.Optimizer,
    step: int,
    loss: float,
    stage: str,
    seed: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "format_version": 1,
        "stage": stage,
        "step": step,
        "loss": loss,
        "seed": seed,
        "config": model.config.to_dict(),
        "model": {key: value.detach().cpu() for key, value in model.state_dict().items()},
        "optimizer": optimizer.state_dict(),
    }
    torch.save(payload, temporary_path)
    temporary_path.replace(path)


def load_initial_weights(model: TinyCausalLM, path: str | None) -> None:
    if not path:
        return
    checkpoint = torch.load(path, map_location="cpu")
    state = checkpoint.get("model", checkpoint)
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing or unexpected:
        raise ValueError(
            f"checkpoint does not match the configured model; missing={missing}, "
            f"unexpected={unexpected}"
        )
    print(f"loaded initial weights from {path}")


def evaluate(
    model: TinyCausalLM,
    loader: DataLoader[dict[str, Tensor]],
    device: torch.device,
    max_batches: int = 10,
) -> float:
    model.eval()
    losses: list[float] = []
    with torch.no_grad():
        for batch_index, batch in enumerate(loader):
            if batch_index >= max_batches:
                break
            batch = {key: value.to(device) for key, value in batch.items()}
            output = model(**batch)
            if output.loss is not None:
                losses.append(float(output.loss.item()))
    model.train()
    return sum(losses) / max(1, len(losses))


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the MiniMind-inspired tiny language model")
    parser.add_argument("--stage", choices=("pretrain", "sft"), required=True)
    parser.add_argument("--data", required=True, help="JSONL training file")
    parser.add_argument("--tokenizer", required=True, help="tokenizer JSON path")
    parser.add_argument("--config", required=True, help="model config JSON path")
    parser.add_argument("--out-dir", default="minillm/runs/experiment")
    parser.add_argument("--init", default=None, help="optional checkpoint to initialize from")
    parser.add_argument("--resume", default=None, help="resume a full checkpoint")
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accumulation", type=int, default=1)
    parser.add_argument("--lr", type=float, default=None)
    parser.add_argument("--warmup-steps", type=int, default=10)
    parser.add_argument("--min-lr-ratio", type=float, default=0.1)
    parser.add_argument("--weight-decay", type=float, default=0.1)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--log-every", type=int, default=10)
    parser.add_argument("--save-every", type=int, default=100)
    parser.add_argument("--eval-every", type=int, default=0)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--cpu-threads", type=int, default=1)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--dtype",
        choices=("float32", "float16", "bfloat16"),
        default="bfloat16",
        help="mixed precision is used only on CUDA",
    )
    args = parser.parse_args()

    if args.max_steps <= 0 or args.grad_accumulation <= 0:
        raise ValueError("max_steps and grad-accumulation must be positive")
    if args.stage == "pretrain" and args.lr is None:
        args.lr = 5e-4
    if args.stage == "sft" and args.lr is None:
        args.lr = 1e-4

    set_seed(args.seed)
    device = torch.device(args.device)
    if device.type == "cpu":
        torch.set_num_threads(max(1, args.cpu_threads))
        torch.set_num_interop_threads(1)
    tokenizer = CharTokenizer.load(args.tokenizer)
    config = ModelConfig.from_json(args.config)
    config.vocab_size = tokenizer.vocab_size
    config.bos_token_id = tokenizer.bos_token_id
    config.eos_token_id = tokenizer.eos_token_id
    config.pad_token_id = tokenizer.pad_token_id

    if args.stage == "pretrain":
        dataset: Dataset[dict[str, Tensor]] = PretrainDataset(
            args.data, tokenizer, config.max_seq_len
        )
    else:
        dataset = SFTDataset(args.data, tokenizer, config.max_seq_len)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=device.type == "cuda",
    )
    eval_loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
    )

    model = TinyCausalLM(config).to(device)
    load_initial_weights(model, args.init)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )
    start_step = 0
    if args.resume:
        checkpoint = torch.load(args.resume, map_location="cpu")
        if checkpoint.get("config") != config.to_dict():
            raise ValueError("resume checkpoint config does not match the requested config")
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        start_step = int(checkpoint.get("step", 0))
        print(f"resuming from step {start_step}")

    amp_enabled = device.type == "cuda" and args.dtype != "float32"
    amp_dtype = torch.float16 if args.dtype == "float16" else torch.bfloat16
    scaler = torch.amp.GradScaler(
        "cuda", enabled=amp_enabled and amp_dtype == torch.float16
    )
    autocast = (
        torch.autocast(device_type="cuda", dtype=amp_dtype)
        if amp_enabled
        else nullcontext()
    )

    print(
        f"stage={args.stage} device={device} parameters={model.num_parameters():,} "
        f"examples={len(dataset)} vocab={tokenizer.vocab_size}"
    )
    print(
        f"batch={args.batch_size} accumulation={args.grad_accumulation} "
        f"effective_batch={args.batch_size * args.grad_accumulation} lr={args.lr}"
    )

    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_iterator = iter_forever(loader)
    model.train()
    optimizer.zero_grad(set_to_none=True)
    started_at = time.time()
    last_loss = float("nan")

    for step in range(start_step + 1, args.max_steps + 1):
        lr = learning_rate_at(
            step,
            args.max_steps,
            args.lr,
            args.warmup_steps,
            args.min_lr_ratio,
        )
        for parameter_group in optimizer.param_groups:
            parameter_group["lr"] = lr

        batch = next(batch_iterator)
        batch = {key: value.to(device, non_blocking=True) for key, value in batch.items()}
        with autocast:
            output = model(**batch)
            if output.loss is None:
                raise RuntimeError("training batch did not produce a loss")
            loss = output.loss / args.grad_accumulation
        if scaler.is_enabled():
            scaler.scale(loss).backward()
        else:
            loss.backward()

        if step % args.grad_accumulation == 0 or step == args.max_steps:
            if scaler.is_enabled():
                scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
            if scaler.is_enabled():
                scaler.step(optimizer)
                scaler.update()
            else:
                optimizer.step()
            optimizer.zero_grad(set_to_none=True)

        last_loss = float(output.loss.detach().item())
        if step == 1 or step % args.log_every == 0 or step == args.max_steps:
            elapsed = time.time() - started_at
            perplexity = math.exp(min(last_loss, 20.0))
            print(
                f"step {step:>6}/{args.max_steps} | loss {last_loss:.4f} | "
                f"ppl {perplexity:.2f} | lr {lr:.2e} | {elapsed:.1f}s"
            )
        if args.eval_every > 0 and step % args.eval_every == 0:
            eval_loss = evaluate(model, eval_loader, device)
            print(f"  eval_loss={eval_loss:.4f} eval_ppl={math.exp(min(eval_loss, 20.0)):.2f}")
        if step % args.save_every == 0 or step == args.max_steps:
            save_checkpoint(
                output_dir / "last.pt",
                model,
                optimizer,
                step,
                last_loss,
                args.stage,
                args.seed,
            )
            print(f"  checkpoint: {output_dir / 'last.pt'}")

    print(f"finished in {time.time() - started_at:.1f}s")


if __name__ == "__main__":
    main()
