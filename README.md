# yiming

当前主线是 **Yiming Lab / Council**：一个建立在成熟 GitHub 项目之上的、本地优先的
「百人圆桌」决策研讨室。

它不重新发明一个孤立的 agent 产品，也不把上游项目整仓复制进来：

```text
- SKILL- 中的书籍 / 人物 skill
        ↓ 每个 skill 一个独立席位
DeepTutor CLI 的隔离进程
        ↓ 首轮并行、互相看不到回答
匿名 blind packet + 主席
        ↓
决策备忘录 / 反对意见 / 证据缺口 / 可逆实验
```

- [Yiming Lab / Council 使用说明](lab/README.md)
- [外部多 Agent 实践检索记录](lab/RESEARCH_NOTES.md)
- [Atlas：冻结的 GitHub 轨迹适配器](atlas/README.md)
- [Atlas / 旧阶段进度](atlas/PROGRESS.md)
- [MiniLLM：早期独立实验](minillm/README.md)

## 最小 dry-run

不需要 API key，也不会调用模型：

```bash
python -m lab council roster --skill-root /path/to/-SKILL- --limit 0
python -m lab council prepare \
  --out "$HOME/.local/share/yiming-lab/councils/<run-id>" \
  --skill-root /path/to/-SKILL- \
  --roster-mode people-books \
  --max-seats 12
python -m lab council run \
  --run "$HOME/.local/share/yiming-lab/councils/<run-id>"
```

只有明确添加 `--execute` 才会调用 DeepTutor；默认 `--max-seats 12`，可显式改成
24 或 `0`（全部匹配席位），但每次调用数、超时和重试上限都必须纳入预算。完整安装、
OpenWiki 接入、匿名审计、结构化 ballot、质量门禁和 66 席全量运行方式见
[`lab/README.md`](lab/README.md)。私有 run 默认写到 Git checkout 之外，不进入本仓库
版本历史。
