from __future__ import annotations

import json
from pathlib import Path
import tempfile

import torch

from .config import ModelConfig
from .data import PretrainDataset, SFTDataset
from .model import TinyCausalLM
from .tokenizer import CharTokenizer


def main() -> None:
    torch.manual_seed(7)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pretrain_path = root / "pretrain.jsonl"
        sft_path = root / "sft.jsonl"
        pretrain_path.write_text(
            json.dumps({"text": "你好，世界。我们正在训练一个小模型。"}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        sft_path.write_text(
            json.dumps(
                {
                    "conversations": [
                        {"role": "user", "content": "你好吗？"},
                        {"role": "assistant", "content": "我很好，谢谢。"},
                    ]
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        tokenizer = CharTokenizer.from_jsonl([pretrain_path, sft_path], vocab_size=128)
        tokenizer_path = root / "tokenizer.json"
        tokenizer.save(tokenizer_path)
        assert CharTokenizer.load(tokenizer_path).decode(
            tokenizer.encode("你好")
        ) == "你好"

        pretrain = PretrainDataset(pretrain_path, tokenizer, max_seq_len=32)
        sft = SFTDataset(sft_path, tokenizer, max_seq_len=32)
        config = ModelConfig(
            vocab_size=tokenizer.vocab_size,
            max_seq_len=32,
            dim=48,
            n_layers=2,
            n_heads=4,
            n_kv_heads=2,
            intermediate_size=128,
        )
        model = TinyCausalLM(config)
        batch = {key: value.unsqueeze(0) for key, value in pretrain[0].items()}
        output = model(**batch)
        assert output.loss is not None and torch.isfinite(output.loss)
        output.loss.backward()
        assert model.num_parameters() > 0

        sft_batch = {key: value.unsqueeze(0) for key, value in sft[0].items()}
        sft_output = model(**sft_batch)
        assert sft_output.loss is not None and torch.isfinite(sft_output.loss)

        prompt = torch.tensor(
            [[tokenizer.bos_token_id, *tokenizer.encode("你好")]], dtype=torch.long
        )
        generated = model.generate(prompt, max_new_tokens=5, temperature=0.0)
        assert generated.shape[1] == prompt.shape[1] + 5

    print("smoke test passed")


if __name__ == "__main__":
    main()
