# MiniLLM：从零训练一个小模型

这是仓库的新主线，与原来的网页内容无关。项目参考 [jingyaogong/minimind](https://github.com/jingyaogong/minimind) 的“从 0 理解完整训练链路”思路，但第一版核心代码自行实现，方便我们逐步阅读、修改和实验。

## 当前状态

已经具备第一阶段的最小闭环：

- 字符级 tokenizer 训练与保存
- Decoder-only Transformer
- RMSNorm、RoPE、SwiGLU
- grouped-query attention（GQA）和 KV cache
- causal language-model next-token loss
- 预训练 JSONL 数据集
- 只对 assistant 回复计算损失的 SFT 数据集
- warmup + cosine learning-rate schedule
- 梯度累积、梯度裁剪、断点保存与恢复
- CPU smoke test 和文本生成命令

字符 tokenizer 是为了让第一版完全少依赖、易调试。MiniMind 主线目前使用更强的 BPE/ByteLevel tokenizer，后续我们会在模型训练闭环稳定后替换它。

## 当前环境策略

当前 Arena 环境检测到：

- Python 3.11
- 没有 NVIDIA GPU，只有 CPU
- 可用内存约 3.8 GiB

因此我们先在这里完成 tiny 模型和完整流程验证；`small.json`、`minimind64.json` 是同一套结构的放大配置，需要 GPU 才适合长时间训练。真正扩大数据和参数时，可以把代码与 checkpoint 搬到 3090/4090 等 CUDA 机器上。

## 安装

建议使用虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r minillm/requirements.txt
```

NVIDIA GPU 请按照 PyTorch 官网选择匹配 CUDA 的安装命令，不要盲目使用 CPU 或不匹配的 wheel。

## 跑通第一条训练链路

在仓库根目录执行：

```bash
# 1. 用预训练文本和 SFT 对话共同建立词表
python -m minillm.prepare \
  --pretrain minillm/data/pretrain_demo.jsonl \
  --sft minillm/data/sft_demo.jsonl \
  --vocab-size 512 \
  --out minillm/artifacts/tokenizer.json

# 2. 检查 tokenizer、forward、反向传播、KV cache 生成
python -m minillm.smoke_test

# 3. CPU 上跑一个很短的预训练实验
python -m minillm.train \
  --stage pretrain \
  --data minillm/data/pretrain_demo.jsonl \
  --tokenizer minillm/artifacts/tokenizer.json \
  --config minillm/configs/tiny.json \
  --out-dir minillm/runs/tiny-pretrain \
  --max-steps 100 \
  --batch-size 4 \
  --save-every 50

# 4. 用预训练权重做 SFT
python -m minillm.train \
  --stage sft \
  --data minillm/data/sft_demo.jsonl \
  --tokenizer minillm/artifacts/tokenizer.json \
  --config minillm/configs/tiny.json \
  --init minillm/runs/tiny-pretrain/last.pt \
  --out-dir minillm/runs/tiny-sft \
  --max-steps 100 \
  --batch-size 2 \
  --lr 1e-4

# 5. 生成一段回答
python -m minillm.generate \
  --checkpoint minillm/runs/tiny-sft/last.pt \
  --tokenizer minillm/artifacts/tokenizer.json \
  --prompt "什么是语言模型？" \
  --max-new-tokens 40 \
  --temperature 0
```

生成的 tokenizer、checkpoint 和实验日志都在 `.gitignore` 中，不会被误提交。

## 数据格式

预训练文件是一行一个 JSON 对象：

```json
{"text": "这是一段用于学习语言规律的文本。"}
```

SFT 文件是一行一个对话：

```json
{"conversations":[
  {"role":"user","content":"请解释预训练。"},
  {"role":"assistant","content":"预训练是在大量文本上学习通用规律。"}
]}
```

当前 demo 数据只是用来验证工程，不代表有意义的训练语料。下一步加入公开数据时，需要先确认许可证、来源和是否允许再分发；私人数据也应该先脱敏。

## 放大模型

在 tokenizer 不变的前提下，可以把 `--config` 换成：

- `configs/tiny.json`：约 0.4M 参数，只用于 CPU smoke test
- `configs/small.json`：约 10M 级，第一轮正式交付的目标配置
- `configs/minimind64.json`：约 64M 级，结构上更接近 MiniMind 的主线规模

模型规模的粗略关系是：词表大小、层数、隐藏维度和 FFN 维度共同决定参数量；训练所需数据量和算力会比参数量增长得更快，所以我们先做小实验并记录 loss、perplexity 和样例输出。10M 版本建议至少使用 8～12 GB 显存；如果显存不足，降低 `--batch-size` 并增加 `--grad-accumulation`。

## 后续路线

1. 用许可清晰的中文公开语料替换 demo 数据，并增加去重、长度过滤和验证集。
2. 将字符 tokenizer 替换为 BPE/ByteLevel tokenizer。
3. 增加独立评测与验证 loss，记录实验配置。
4. 在 GPU 上训练 small，再尝试 64M。
5. 增加更完整的 chat template、DPO，以及可选的工具调用能力。
