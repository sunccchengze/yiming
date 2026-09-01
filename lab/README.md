# Yiming Lab / Council

> 一个建立在成熟项目之上的、本地优先的「百人圆桌」适配层。

Yiming Council 不把每本书、每个人重新实现成一套 agent framework。它把
`sunccchengze/-SKILL-` 中的蒸馏 skill 解析成独立席位，再用 DeepTutor CLI
做隔离运行时，用 OpenWiki 提供项目事实底座，用 `-SKILL-` 的路由与研究门禁
约束最后的综合。

## 先说清楚：subagent 权限

当前 Arena 工具面板没有直接暴露原生 `spawn_subagent` API。因此本实现使用
**一个 DeepTutor CLI 进程 = 一个独立席位**：

- 每个席位只收到共同事实、自己的 skill brief 和同一个问题；
- 第一轮用并行进程扇出，席位不读取其他席位的 prompt/output；
- 每个席位拥有独立的 `DEEPTUTOR_HOME`，不共享 session、memory 或 notebook；
- 所有席位结束后才建立不含姓名的 `blind-packet.json`；
- 证据、分歧、行动三个 reviewer 只读匿名提案，分别找无证据断言、最强少数意见和不可逆动作；
- 主席只读匿名提案与 reviewer notes，并输出最终决策 memo；
- `prepare` 和默认 `run` 都不调用模型，只有明确加 `--execute` 才会产生模型调用。

这比让一群 agent 一开始就聊天更适合“百人圆桌”：先保留真正的异议，再让
主席做归纳，减少第一个回答对后续回答的锚定。

## 当前 roster

`people-books` 模式会发现：

- `skills/community/nuwa-distilled/**/book-*/SKILL.md`：蒸馏书籍；
- `skills/community/nuwa-distilled/**/*perspective*/SKILL.md`：蒸馏人物视角；
- `skills/community/nuwa-skill/examples/*perspective*/SKILL.md`：人物视角示例；
- `skills/core/*perspective*/SKILL.md`：核心人物视角。

在本次固定的两个 `-SKILL-` checkout 上，当前发现 **66 个席位：33 本书 +
33 个人物视角**。这是运行时扫描结果，不是写死的名单；skill 仓库更新后，
先重新运行 `council roster` 审阅变更。

```bash
python -m lab council roster \
  --skill-root /path/to/skill-arena-01a048e7 \
  --skill-root /path/to/skill-main \
  --roster-mode people-books \
  --limit 0
```

`--roster-mode distilled` 会额外纳入 Nuwa 蒸馏的方法类 skill；`all` 会扫描
提供的 checkout 中所有 `SKILL.md`，适合实验，不建议默认直接跑满。

## 快速开始：先做无 key 的完整 dry-run

### 1. 准备两个 skill checkout

OpenWiki、DeepTutor 和治理文件在一个固定工作分支；
`sun-chengze-perspective` 在 `main`。这是上游分支事实，所以命令明确保留
两个来源，而不是假装它们属于同一个 snapshot：

```bash
git clone --depth=1 --branch arena/01a048e7-skill \
  https://github.com/sunccchengze/-SKILL-.git \
  /path/to/skill-arena-01a048e7

git clone --depth=1 --branch main \
  https://github.com/sunccchengze/-SKILL-.git \
  /path/to/skill-main
```

### 2. 生成私有项目事实包

输出目录放在 Git checkout 外；默认不复制源码，只有显式加
`--include-corpus` 才会把已经采集的安全记录放入本地包：

```bash
python -m lab prepare \
  --inventory minillm/artifacts/account_inventory.json \
  --out "$HOME/.local/share/yiming-lab/runs/$(date -u +%Y%m%dT%H%M%SZ)" \
  --skill-root /path/to/skill-arena-01a048e7 \
  --perspective-root /path/to/skill-main \
  --repo yiming="$PWD"
```

命令只会写 `run.json`、Markdown source pack、OpenWiki 本地 connector 配置和
`RUN_PLAN.md`。它不会自动联网、调用模型或写 `~/.openwiki`。

### 3. 准备百人圆桌

```bash
python -m lab council prepare \
  --out "$HOME/.local/share/yiming-lab/councils/$(date -u +%Y%m%dT%H%M%SZ)" \
  --skill-root /path/to/skill-arena-01a048e7 \
  --skill-root /path/to/skill-main \
  --roster-mode people-books \
  --max-seats 0 \
  --reviewer-count 3 \
  --source-pack /path/to/the/run/source-pack \
  --task '从我最近的项目轨迹中找出最值得做的下一个研究实验，比较方案，保留强烈反对意见。'
```

`--max-seats 0` 表示全部匹配席位。第一次试跑建议 `--max-seats 5` 或 `12`，
确认 prompt、成本和输出格式后再开 66 席。

### 4. 只查看执行计划

```bash
python -m lab council run \
  --run "$HOME/.local/share/yiming-lab/councils/<run-id>"
```

### 5. 配好 DeepTutor 后才真正执行

```bash
# 安装版本以实际运行条件为准；不要把 provider key 写进仓库。
pip install 'deeptutor[cli]==1.6.2'

python -m lab council run \
  --run "$HOME/.local/share/yiming-lab/councils/<run-id>" \
  --execute \
  --workers 8
```

席位阶段是 `N` 次并行调用，接着最多 3 次盲 reviewer，最后主席再调用 1 次；
所以“百人”不是无成本修辞。执行前应先看 `COUNCIL_PLAN.md`，用 `--max-seats`、
`--reviewer-count`、`--workers` 和 `--max-calls` 控制预算。默认最多 12 个席位、
每次调用 1 个 attempt；只有显式设置 `--max-attempts` 才会重试失败/超时调用。
这只是调用数/超时预算，不等于 provider 的 token 账单；通用 CLI 没有可靠的跨模型
token 计量，因此不伪造成本数字。每个席位的失败、stderr、stdout 和每次 attempt
都会落在该席位自己的目录里，不会让其他席位看到它的中间结果。中途失败后可以
加 `--resume`，只重跑缺失/失败的席位，再重新审查 blind packet。

### 5b. 用任意模型 runner（不依赖 DeepTutor）

如果不用 DeepTutor，可以用 `--runner` 指定一个 shell 命令模板来驱动每个
席位/reviewer/chair，例如你的 Claude Code harness + DeepSeek：

```bash
# 方式 B：Claude Code CLI 指向 DeepSeek
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_API_KEY"
export ANTHROPIC_MODEL="deepseek-chat"

python -m lab council run \
  --run "<run-id>" \
  --execute \
  --runner "$(pwd)/lab/examples/runner-claude-deepseek.sh" \
  --workers 4 --timeout-seconds 900
```

`--runner` 是一个 shell 模板，占位符：

- `{prompt}` 完整 prompt 文本（shell 转义）
- `{prompt_file}` prompt .md 的绝对路径
- `{stage}` `independent-seat` / `blind-reviewer` / `chair`

prompt 同时会通过 stdin 传入，并暴露 `$YIMING_PROMPT_FILE`、`$YIMING_PROMPT_STAGE`，
方便 wrapper 脚本读取。示例 wrapper 见 `lab/examples/runner-claude-deepseek.sh`。
默认（不加 `--runner`）仍走 DeepTutor：`deeptutor run chat <prompt> --language zh --format json`。

> 完整启动流程、结果解读与安全边界见 [`lab/RUNBOOK.md`](RUNBOOK.md)。

## 目录与制品

```text
<private-run>/
├── council.json             # 协议、路由、隐私和调用预算
├── roster.json              # 发现到的席位、源路径、文件 hash
├── COUNCIL_PLAN.md          # 不执行的审阅计划
├── seats/<seat-id>/
│   ├── prompt.md            # 该席位唯一能看到的输入
│   ├── stdout.log           # 模型原始输出
│   └── stderr.log           # 失败/诊断
├── runtime/seats/<seat-id>/ # 每席位独立 DEEPTUTOR_HOME
├── blind-packet.json        # 去姓名后的提案，供 reviewer/主席读取
├── blind-map.json            # 本地私有 P### ↔ seat 映射；不传给 reviewer/主席
├── reviewers/<reviewer-id>/ # evidence / dissent / action reviewer
├── reviewer-results.json
├── reviewer-ballots.json     # reviewer 结构化审查（缺字段不补）
├── ballots.json               # seat 结构化 ballot 与透明加权分数
├── DISSENT_LEDGER.md          # 少数意见、反例和未决问题
├── decision-record.json       # 从主席原文提取的共识/异议/证据/实验记录
├── quality-gates.json         # 协议与输出结构门禁；仍需人工 review
├── isolation-audit.json       # 输入 hash、cwd、DEEPTUTOR_HOME、peer withheld 证据
├── chair/
│   ├── prompt.md
│   ├── stdout.log
│   ├── attempt-*/
│   └── final.md
└── result.json
```

Yiming Lab 的普通 source pack 还包含：

- `projects/`：从账号 inventory 生成的项目/branch/commit 事实卡；
- `research/RESEARCH_CHARTER.md`：人工在环章程；
- `research/EVIDENCE_TABLE.md`、`CLAIM_SOURCE_MAP.md`：证据和 claim 门禁；
- `source-pack/_skills/`：仅选中的 policy skill 副本及 hash；
- `integrations/openwiki-git-repo-config.json`：只包含本地路径，不包含 secret。

## 结构化输出怎样被解释

`ballots.json` 只在 seat 自己提供 `<ballot>` JSON 且字段完整时计算透明分数：
`evidence=35%`、`expected_value=20%`、`reversibility=20%`、
`actionability=25%`，每项 0–5。`confidence` 单独保存，不参与“事实可信度”
计算；缺字段不会被当成 0，也不会被当成反对。`decision-record.json` 从主席原文
提取以下人工可读字段：共识、最强少数意见、证据缺口、可逆实验、停止条件和置信度。
解析失败就写入 `missing_sections`，而不是生成一个看似完整的结论。

`quality-gates.json` 会检查 roster provenance、首轮 prompt 是否夹带 peer output、
blind packet 是否泄漏 seat 身份、reviewer 是否齐全和主席 memo 是否具备必需段落。
它的 `pass` 只代表协议/制品检查通过，绝不代表建议正确；`DISSENT_LEDGER.md`
仍要求用户在任何外部行动前阅读并批准。

## 用到的 skill 及其边界

本适配层实际读取并 attestation 的最小组是：

| 角色 | Skill | 用法 |
|---|---|---|
| 主底座 | `openwiki` | 项目/个人 Wiki 的真实 CLI 与本地 git connector |
| 支撑 | `DeepTutor` | `run`、知识库、研究、问题和记忆的 CLI 接口 |
| 支撑 | `sun-chengze-perspective` | 只作决策校准镜，不冒充本人 |
| 支撑 | `research-workflow-kit` | charter、evidence table、claim-source map、人工 review |
| 审查 | `QUALITY_GATES` | 事实、接口、隐私、许可、运行证据和交付检查 |
| 协调 | `universal-skill-router` | 将任务压缩到最小技能组，不加载整个 skill 仓库 |

`run.json` 会记录每个入口文件的 SHA-256、字节数、行数和实际来源路径，以及选中
policy skill 的 Git branch、tip commit 和 dirty state；`roster.json` 还记录每席位的
稳定 ID 规则、Git branch、tip commit 和 dirty state。
准备阶段只读 `SKILL.md`，不自动执行其中的脚本。席位 brief 把 skill 内容放在
`<lens-reference>` 边界内，当作参考材料而不是可执行指令。人物席位还带有
`analytical_person_lens_not_person_statement` 标记，不能被解读为真人本人发言。

## 上游来源与改动边界

| 来源 | 固定版本/来源 | 许可证 | 在本项目中的角色 |
|---|---|---|---|
| [OpenWiki](https://github.com/langchain-ai/openwiki) | npm `0.3.2`；Node `>=22` | MIT | 外部安装/运行；本项目只生成 connector 配置和 run plan |
| [DeepTutor](https://github.com/HKUDS/DeepTutor) | PyPI `1.6.2`；Python `3.11+` | Apache-2.0 | 外部安装/运行；本项目只并行调用 CLI、隔离 home、保存结果 |
| [`-SKILL-`](https://github.com/sunccchengze/-SKILL-) | `arena/01a048e7-skill@4cbe659` | 依各文件/仓库声明 | OpenWiki、DeepTutor skill、router、research workflow、quality gates |
| [`-SKILL-`](https://github.com/sunccchengze/-SKILL-) | `main@0da485b` | 依各文件/仓库声明 | `sun-chengze-perspective` 的当前来源 |

没有把 OpenWiki、DeepTutor 或 `-SKILL-` 整仓复制到 `yiming`。新代码只负责
发现席位、生成隔离 prompt、并行 CLI 调度、盲包和质量/隐私边界。

## 从外部实践借鉴了什么

参考了公开的 AgentCouncil、Senate 和 multi-agent-debate 实践，但没有复制它们
的代码：

- 独立首轮，再进入共享/综合阶段；
- 固定轮数、并发数和超时，避免开放式聊天无限消耗；
- 自定义角色 brief，而不是启动没有领域上下文的 generic agent；
- 结构化 transcript / run directory / judge 输出；
- 让主席看到匿名提案，并保留 dissent，而不是只输出多数意见。

更详细的检索记录见 [`RESEARCH_NOTES.md`](RESEARCH_NOTES.md)。

## 局限与未验证项

- Arena 没有原生 subagent 工具，所以当前后端是 DeepTutor CLI 进程，不是平台级
  subagent；`isolation-audit.json` 是 adapter 边界的可审计证明，不宣称 OS sandbox；
- 本仓库已验证 roster provenance、prompt 隔离、身份去标识盲包、结构化 ballot、
  私有输出、调用预算和无 key dry-run；
- 尚未在本环境用真实 provider 跑完 66 个 DeepTutor 席位；这需要用户自己的
  provider 配置并会产生模型费用；
- OpenWiki npm CLI 已在 Node 22 环境显示帮助，但本地 `better-sqlite3` 安装
  需要可用 headers/build tool；
- “百人圆桌”首个版本是独立提案 + 匿名 reviewer + 匿名主席，不是 66 个 agent
  互相聊天；这是有意选择的抗锚定协议，后续可以加入受限的反驳轮，但不能默认打开；
- 结构化 ballot 是模型自报的决策支持指标，只有字段完整时才计算加权分数；它不是
  事实可信度、投票胜负或真人意志的替代品；

## 验证

```bash
python -m compileall -q lab
python -m unittest -v lab.test_lab
python -m lab --help
```
