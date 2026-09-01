# Yiming Council 启动手册（RUNBOOK）

> 本文件回答一个问题：**怎么真正把这个圆桌跑起来。**
> 前提：在你的**本机**（有正常外网、能访问模型 API）上运行。此适配层只负责
> 扇出独立席位 → 匿名盲审 → 主席综合，并全程生成可审计的本地制品。

---

## 0. 快速理解：圆桌是什么、怎么"启动"

```text
一个问题
  ├─ 每本书/每个人物 = 一个独立分析席位（analytical lens，不是真人）
  ├─ 第一轮：每个席位独立回答，彼此看不到对方
  ├─ 匿名 reviewer：找证据缺口、最强少数意见、行动风险
  └─ chair：综合共识、冲突、dissent、可逆实验和停止条件
```

"启动圆桌" = 跑两个命令：

```bash
python -m lab council prepare  ...   # 无模型：生成席位 prompt 和计划
python -m lab council run      ...   # 真正执行：调用模型跑席位/reviewer/chair
```

`prepare` 永远不会调用模型、不花钱。`run` 只有加 `--execute` 才会调用模型（产生费用）。

---

## 1. 准备两个 skill checkout

座位的来源是你的 `-SKILL-` 仓库（蒸馏书籍 + 人物视角）。两个分支必须分开，
因为它们不是同一个 snapshot：

```bash
mkdir -p ~/yiming-skills && cd ~/yiming-skills
git clone --depth=1 --branch arena/01a048e7-skill \
  https://github.com/sunccchengze/-SKILL-.git skill-arena-01a048e7
git clone --depth=1 --branch main \
  https://github.com/sunccchengze/-SKILL-.git skill-main
git -C skill-arena-01a048e7 rev-parse HEAD   # 预期 4cbe659...
git -C skill-main rev-parse HEAD             # 预期 0da485b...
```

> 这些 checkout 放在 `yiming` 仓库外，内容不会被 commit。

---

## 2. 安装适配层（在本机）

```bash
cd /path/to/yiming
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                      # 若没有 pyproject，则 pip install -e ".[dev]" 或直接源码运行
python -m compileall -q lab
python -m unittest lab.test_lab        # 期望 12 tests OK
```

---

## 3. 选择模型后端（二选一）

### 方式 A：DeepTutor CLI（默认，推荐先跑通）

```bash
pip install 'deeptutor[cli]==1.6.2'
deeptutor init --cli          # 交互式：选 DeepSeek / 填 key / 填 deepseek-chat
# 或直接写 DeepTutor 的 model_catalog.json（放其数据目录，勿提交仓库）
```

之后 `run` 用默认 `--deeptutor-bin deeptutor` 即可。

### 方式 B：Claude Code harness + DeepSeek（`--runner`）

适配层现在支持任意模型命令模板（`--runner`），不依赖 DeepTutor。仓库已附示例
wrapper：`lab/examples/runner-claude-deepseek.sh`。用法：

```bash
# 一次性配置 Claude Code CLI 指向 DeepSeek
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_API_KEY"   # 你的 DeepSeek key
export ANTHROPIC_MODEL="deepseek-chat"            # 或 deepseek-reasoner
# 验证一次：
echo "hi" | claude -p --output-format text

# 跑圆桌时这样传 runner：
python -m lab council run --run <RUN_DIR> --execute \
  --runner "$(pwd)/lab/examples/runner-claude-deepseek.sh" \
  --workers 4 --timeout-seconds 900
```

`--runner` 模板支持的占位符（直接内联也可，不必用脚本）：

| 占位符 | 含义 |
|---|---|
| `{prompt}` | 完整 prompt 文本（shell 转义）|
| `{prompt_file}` | 生成的 prompt .md 的绝对路径 |
| `{stage}` | `independent-seat` / `blind-reviewer` / `chair` |

prompt 还会通过 stdin 传入，并暴露 `$YIMING_PROMPT_FILE` / `$YIMING_PROMPT_STAGE`，
方便 wrapper 脚本读取。

> 安全：`--runner` 使用 `shell=True` 执行你提供的模板。它是你自己的配置，但请
> 只使用可信模板，不要直接拼接不受信的用户输入。

---

## 4. 启动：完整命令序列

### 4.1 先看 roster（只读，0 费用）

```bash
SKILLS=/home/USER/yiming-skills
python -m lab council roster \
  --skill-root "$SKILLS/skill-arena-01a048e7" \
  --skill-root "$SKILLS/skill-main" \
  --roster-mode people-books --limit 0 --json
```

预期 **66 席 = 33 本书 + 33 个人物视角**（以实际扫描为准，别盲信旧数字）。

### 4.2 准备 5 席（无模型，0 费用）

```bash
RUN="$HOME/.local/share/yiming-lab/councils/$(date -u +%Y%m%dT%H%M%SZ)"
python -m lab council prepare \
  --out "$RUN" \
  --skill-root "$SKILLS/skill-arena-01a048e7" \
  --skill-root "$SKILLS/skill-main" \
  --roster-mode people-books \
  --max-seats 5 --reviewer-count 3 --max-attempts 1 \
  --task '从我最近的项目轨迹中找出最值得做的下一个研究实验，比较方案，保留强烈反对意见。'
```

查看 `$RUN/COUNCIL_PLAN.md`：确认 5 席 + 3 reviewer + 1 chair = 9 次调用。

### 4.3 dry-run（不调用模型）

```bash
python -m lab council run --run "$RUN"                      # 方式 A（deeptutor）
python -m lab council run --run "$RUN" --runner '<你的模板>' # 方式 B
```

### 4.4 真正执行（第一次用 5 席）

```bash
# 方式 A
python -m lab council run --run "$RUN" --execute --workers 4 --max-calls 40

# 方式 B
python -m lab council run --run "$RUN" --execute \
  --runner "$(pwd)/lab/examples/runner-claude-deepseek.sh" \
  --workers 4 --max-calls 40 --timeout-seconds 900
```

中途失败可 `--resume`，只重跑失败/缺失席位，成功席位 stdout 复用。

---

## 5. 读结果（这是最重要的部分）

跑完去看 `$RUN/` 下的文件：

| 文件 | 看什么 |
|---|---|
| `COUNCIL_PLAN.md` | 执行前审阅计划、席位清单、预算 |
| `blind-packet.json` | 去姓名匿名提案（P001…P005）|
| `blind-map.json` | **私有** 的 P### ↔ 真实席位映射，别外发 |
| `reviewer-results.json` | evidence / dissent / action 三位盲审 |
| `DISSENT_LEDGER.md` | 少数意见、反例、未决问题（**必读**）|
| `decision-record.json` | 主席原文解析出的共识/异议/证据缺口/实验 |
| `chair/final.md` | 主席原始决策备忘录 |
| `quality-gates.json` | 协议/制品门禁（pass 不代表建议正确）|
| `isolation-audit.json` | 输入 hash、cwd、独立 home、peer withheld 证据 |

**行动纪律**：任何外部行动前，人工读完 `DISSENT_LEDGER.md`、
`decision-record.json`、`quality-gates.json` 再决定。

---

## 6. 从小规模到"百人"

1. 先 3–5 席，看输出质量和成本；
2. 满意后 12 席（`--max-seats 12`）；
3. 只有 Phase C 通过后，才考虑 66 席（`--max-seats 0` 或显式 66）。

"百人"= 66/100 次并行模型调用 + 3 次 reviewer + 1 次 chair。费用随席位线性增长，
DeepSeek 很便宜但也不是零。务必用 `--max-calls`、`--workers`、`--timeout-seconds`
控制预算。

---

## 7. 安全边界（务必遵守）

- 模型调用是显式副作用：无 `--execute` 不调用。
- 私有输出（run 目录、skill 副本、DeepTutor home、key）放在 Git checkout 外，
  绝不 commit。
- 不传播 secrets：key 只写进本机配置，日志只记 key 名称/状态，不记值。
- 人物席位是分析镜，不代表真人或书作者发言。
- ballot 是模型自报的结构化决策支持，缺字段不补零，少数意见与 abstain 保留。
- 匿名不是 OS sandbox：`isolation-audit.json` 只证明适配层未注入 peer output，
  宿主工具/provider 的真实权限仍需另行审计。

---

## 8. 常见问题

- **`no council seats found`**：`--skill-root` 路径不对，或 checkout 为空。
- **`No active LLM model is configured`**（DeepTutor）：还没在 Settings > Catalog
  配好模型/profile。
- **runner 没输出/超时**：先手动验证 `echo "hi" | claude -p --output-format text`。
- **某个席位失败**：该席位 `stderr.log` 保留失败原因；`--resume` 只重跑失败席位。
