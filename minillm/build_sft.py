from __future__ import annotations

"""Turn collected project records into small, local SFT examples.

This is deliberately template-based rather than pretending an external model
summarized the repositories.  It gives the first model project vocabulary and
an instruction format; a later pass can replace the templates with reviewed,
handwritten answers.
"""

import argparse
import json
from pathlib import Path

from .tokenizer import read_jsonl


def shorten(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n……（内容已截断）"


def build(input_path: Path, output_path: Path, max_examples: int, max_response_chars: int) -> int:
    records = list(read_jsonl(input_path))
    examples: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        kind = record.get("kind")
        repo = str(record.get("repo", "未知仓库"))
        branch = str(record.get("branch", "未知分支"))
        if kind == "commit_summary":
            key = ("commit", repo, str(record.get("commit", "")))
            if key in seen:
                continue
            seen.add(key)
            response = shorten(str(record.get("text", "")), max_response_chars)
            user = f"请整理项目 {repo} 分支 {branch} 的这条近期开发记录。"
        elif kind == "repository_file":
            path = str(record.get("path", "未知文件"))
            # README/docs are more useful for early SFT than generated bundles.
            lower_path = path.lower()
            if not (
                lower_path.startswith("readme")
                or "/readme" in lower_path
                or "/docs/" in f"/{lower_path}/"
                or lower_path.endswith((".md", ".txt"))
            ):
                continue
            key = ("file", repo, path)
            if key in seen:
                continue
            seen.add(key)
            raw_text = str(record.get("text", ""))
            if "文件内容：\n" in raw_text:
                raw_text = raw_text.split("文件内容：\n", 1)[1]
            response = shorten(raw_text, max_response_chars)
            user = f"请根据项目资料介绍 {repo} 中的文件 {path}。"
        else:
            continue
        if not response:
            continue
        examples.append(
            {
                "conversations": [
                    {
                        "role": "system",
                        "content": "你熟悉这些项目的代码、文档和开发历史，请基于资料准确回答。",
                    },
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": response},
                ]
            }
        )
        if len(examples) >= max_examples:
            break

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(example, ensure_ascii=False) + "\n")
    print(f"SFT 数据已写入：{output_path}")
    print(f"examples={len(examples)}")
    return len(examples)


def main() -> None:
    parser = argparse.ArgumentParser(description="从 GitHub 项目语料生成模板化 SFT 数据")
    parser.add_argument("--input", required=True, help="github_corpus.jsonl")
    parser.add_argument("--out", required=True, help="输出 SFT JSONL")
    parser.add_argument("--max-examples", type=int, default=1000)
    parser.add_argument("--max-response-chars", type=int, default=3000)
    args = parser.parse_args()
    build(Path(args.input), Path(args.out), args.max_examples, args.max_response_chars)


if __name__ == "__main__":
    main()
