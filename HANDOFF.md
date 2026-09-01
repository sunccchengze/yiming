# HANDOFF — Yiming Lab / Council

> 交接给下一位 Agent。当前 Agent 在写完本文件后停止，不继续执行 Phase A–F，不调用模型，不读取新的私有语料。

## 0. 交接状态

- 仓库：`sunccchengze/yiming`
- 固定工作分支：`arena/01a05b71-yiming`
- 当前 HEAD：`68b7d63 Record roundtable checkpoint and approval plan`
- 远端：`origin/arena/01a05b71-yiming`
- 当前工作树：应保持干净
- 交接日期：2026-09-01（Asia/Shanghai）
- 用户最新指令：**进行 HANDOFF，剩下的交给其他 agent**

不要切换、创建或 push 到其他分支。

## 1. 用户要做什么

用户希望把自己 `sunccchengze/-SKILL-` 仓库里蒸馏过的书籍、人物和方法，变成一场可审计的独立视角决策研讨室：

```text
一个问题
  ├─ 每本书/每个人物是一个独立 analytical lens
  ├─ 第一轮并行回答，彼此看不到 prompt/output
  ├─ 匿名 reviewer 审查提案、证据缺口、少数意见和行动风险
  └─ 最后由 chair 综合共识、冲突、dissent、实验和停止条件
```

“百人圆桌”是显式的大规模运行模式，不是默认每次都把所有 seat 跑满。
Seat 是分析镜，不是实际人物、作者或用户本人的发言器。

## 2. 已完成的实现，不要重写

核心代码已经存在于 `lab/`，不要重新从零搭一个 council framework：

- `lab/council.py`
  - 只读扫描本地 `-SKILL-` checkout；
  - `people-books` / `distilled` / `all` roster mode；
  - 稳定 seat ID：`kind + relative_path + file_sha256`；
  - 记录 source root、branch、tip commit、dirty state、文件 hash、行数和 lens policy。
- `lab/council_protocol.py`
  - model-free `prepare`；
  - 每个 seat 独立 prompt、cwd、`DEEPTUTOR_HOME`、stdout/stderr 和 attempt 目录；
  - 第一轮完成后才生成 `blind-packet.json`；
  - `blind-map.json` 仅本地保存真实 seat 映射；
  - evidence / dissent / action reviewer；
  - chair；
  - `--resume`、失败保留、调用/重试/并发/超时预算。
- `lab/council_records.py`
  - ballot、reviewer ballot、chair sections、decision record、quality gate；
  - 缺字段不补零，不把缺失解释为反对或共识。
- `lab/pipeline.py`
  - 本地项目事实包；
  - OpenWiki local-git connector 配置；
  - DeepTutor KB / run plan；
  - 默认禁止把私有制品输出到 Git checkout。
- `lab/routing.py` / `lab/skills.py`
  - 最小技能组路由；
  - DeepTutor capability/tool 配置；
  - `sun-chengze-perspective` 只作决策校准镜；
  - quality/evidence 约束。
- `lab/test_lab.py`
  - 当前 10 个针对性测试。

入口：

```bash
python -m lab --help
python -m lab council roster --help
python -m lab council prepare --help
python -m lab council run --help
```

完整使用说明：[`lab/README.md`](lab/README.md)
阶段计划与确认边界：[`lab/CHECKPOINT.md`](lab/CHECKPOINT.md)
外部检索记录：[`lab/RESEARCH_NOTES.md`](lab/RESEARCH_NOTES.md)

## 3. 已推送里程碑

```text
9b5e694 Add independent skill council adapter
 d217134 Add blind reviewers and resumable council runs
 ab70eb2 Document subagent design sources
 f1e87a7 Add council provenance ballots and quality gates
 68b7d63 Record roundtable checkpoint and approval plan
```

`68b7d63` 之前的 4 个 council 相关提交已经在远端 branch 上。不要因为一个新的
Arena 工作回合 materialize 到 `300309f` 基线，就判断这些工作不存在；先执行：

```bash
git fetch origin arena/01a05b71-yiming
git reset --hard origin/arena/01a05b71-yiming
```

只在确认工作树没有用户新改动时执行 reset。固定分支不变。

## 4. 已验证事实

最近在 `f1e87a7` 上重新验证过：

```text
python -m compileall -q lab       PASS
python -m unittest -v lab.test_lab PASS — 10 tests
python -m lab --help              PASS
```

测试覆盖 roster provenance、独立 home、prompt isolation、blind packet、匿名映射、
reviewer/chair 读取边界、structured ballot、resume、预算、private-output 拒绝和
无 key dry-run。

当前还没有完成的验证：

- 没有用真实 provider 跑完 66 个 seat；
- 没有允许 `--execute` 产生真实模型账单；
- 没有把任何东西安装进用户的 `~/.claude/agents`、`~/.openwiki` 或其他 Agent 目录；
- 没有重新在本回合下载两个 `-SKILL-` checkout。之前用于验证的 `/tmp` clone 是临时的，
  下一位 Agent 必须重新定位或 clone，并记录 branch/tip SHA；
- “66 个 seat：33 本书 + 33 个人物视角”是当前文档记录的预期值，必须用实际 checkout
  重新跑 `roster`，不能盲信旧数字。

## 5. 外部底座和固定来源

不要复制成熟项目整仓。当前组合边界如下：

| 来源 | 固定版本/事实 | 用法 |
|---|---|---|
| [OpenWiki](https://github.com/langchain-ai/openwiki) | npm `0.3.2`，Node `>=22`，MIT | 项目/个人 wiki 和 local-git connector；Yiming 只生成配置/计划 |
| [DeepTutor](https://github.com/HKUDS/DeepTutor) | PyPI `1.6.2`，Python `>=3.11,<3.14`，Apache-2.0 | 每席隔离 CLI runtime、reviewer、chair、KB、research |
| [Council of High Intelligence](https://github.com/0xNyk/council-of-high-intelligence) | 上游 tip `502ceda82050d607cbef88078a69b07084835410`，MIT，18 个已有 lens | 协议参考：独立首轮、匿名审查、dissent、预算、provider routing；不盲拷贝 |
| [Karpathy llm-council](https://github.com/karpathy/llm-council) | 并行回答 → 匿名互评 → chair；当前 license 信息未确认 | 仅方法论参考，不作为代码依赖 |
| `-SKILL-` `arena/01a048e7-skill@4cbe659` | 含 OpenWiki/DeepTutor skill、universal router、research workflow、quality gates | 主适配来源 |
| `-SKILL-` `main@0da485b45aad600fe98e7316885a094ea508cfaa` | 含 `sun-chengze-perspective` | 个人决策校准镜，默认只读 `SKILL.md` |

详细来源、X/GitHub 检索和没有采用的方案见 `lab/RESEARCH_NOTES.md`。

## 6. 下一位 Agent 的推荐执行顺序

### Step 1 — 先恢复真实 branch 状态

```bash
git status --short
git log --oneline --decorate -8
git fetch origin arena/01a05b71-yiming
git reset --hard origin/arena/01a05b71-yiming
```

如果有非本次 Agent 的新改动，先停下来，不要覆盖。

### Step 2 — 准备并记录两个 skill checkout

建议不要把它们放入当前仓库，也不要把内容 commit：

```bash
git clone --depth=1 --branch arena/01a048e7-skill \
  https://github.com/sunccchengze/-SKILL-.git /some/private/path/skill-arena-01a048e7

git clone --depth=1 --branch main \
  https://github.com/sunccchengze/-SKILL-.git /some/private/path/skill-main

git -C /some/private/path/skill-arena-01a048e7 rev-parse HEAD
git -C /some/private/path/skill-main rev-parse HEAD
```

OpenWiki/DeepTutor/router/governance 与个人 perspective 不在同一 branch，不能假装是
一个 snapshot。

### Step 3 — 重新核对 roster（只读）

```bash
python -m lab council roster \
  --skill-root /some/private/path/skill-arena-01a048e7 \
  --skill-root /some/private/path/skill-main \
  --roster-mode people-books \
  --limit 0 \
  --json
```

确认 books/people/count、每个 source branch/tip SHA、dirty state。只读取目标包的
`SKILL.md`、LICENSE/NOTICE 和必要 provenance；默认不要读取 `memory/`、访谈原文或
references。

### Step 4 — 先做 5-seat model-free prepare

输出必须在 checkout 外：

```bash
python -m lab council prepare \
  --out "$HOME/.local/share/yiming-lab/councils/<UTC-run-id>" \
  --skill-root /some/private/path/skill-arena-01a048e7 \
  --skill-root /some/private/path/skill-main \
  --roster-mode people-books \
  --max-seats 5 \
  --reviewer-count 3 \
  --max-attempts 1 \
  --task '从我最近的项目轨迹中找出最值得做的下一个研究实验，比较方案，保留强烈反对意见。'
```

这一步不能调用模型。检查：

- `COUNCIL_PLAN.md`；
- `council.json` / `roster.json`；
- 每个 `seats/<id>/prompt.md`；
- 每个 seat 独立 `runtime/seats/<id>/`；
- `peer_output_injected=false`；
- 预算：5 seat + 3 reviewer + 1 chair，重试次数明确；
- 所有 output 路径在 Git checkout 外。

### Step 5 — 做 dry-run/fake-runtime E2E

```bash
python -m lab council run \
  --run "$HOME/.local/share/yiming-lab/councils/<UTC-run-id>"
```

然后使用本地 fake `deeptutor` executable 验证执行路径，不发网络请求：

- seat stdout/stderr/attempt 可持久化；
- blind packet 在所有 seat 完成后才创建；
- reviewer/chair 只能看到规定输入；
- blind-map 不进入 reviewer/chair prompt；
- `--resume` 只复用已成功 stdout；
- 失败不伪装成共识；
- `quality-gates.json` 和 `DISSENT_LEDGER.md` 正确记录未验证项。

### Step 6 — 真实运行前必须再次确认

真实调用前需要：

- 用户明确允许真实模型调用；
- 用户配置了 DeepTutor provider；
- 明确 `--workers`、`--timeout-seconds`、`--max-attempts`、`--max-calls`；
- 先 3–5 席，不直接跑 66/100；
- 用户/人工阅读 dissent、evidence gaps 和 quality gates；
- 不自动写其他 Agent 配置，不自动发布或执行外部行动。

## 7. 重要安全边界

1. **模型调用是显式副作用**：无 `--execute` 不调用；不要把 dry-run 结果说成真实结论。
2. **私人输出不进 Git**：run、source pack、个人 skill 副本、DeepTutor home、模型日志
   默认放在 `$HOME/.local/share/yiming-lab` 或其他 checkout 外目录。
3. **不传播 secrets**：不读取 `.env`、token、私钥、密码或原始 credential；日志只记录
   key 名称/状态，不记录值。
4. **不冒充人物/作者/用户**：人物 seat 只表达方法 lens；必须保留
   `analytical_person_lens_not_person_statement` 边界。
5. **匿名不是 OS sandbox**：`isolation-audit.json` 证明 adapter 未向首轮注入 peer
   output，但 DeepTutor/provider/宿主工具的真实权限仍需另外审计。
6. **不把投票当真理**：ballot 是模型自报的结构化决策支持指标；缺字段不补零，少数意见
   与 abstain 必须保留。
7. **不默认“百人”**：多席位会线性增加调用数和费用；Anthropic 的公开经验也强调
   多 agent 适合可拆分的 breadth-first 问题，不适合紧耦合、强顺序任务。
8. **不继续扩展 Atlas UI**：Atlas 仅作为 GitHub 轨迹适配器候选，除非新改动直接服务于
   OpenWiki/DeepTutor/Council 集成。

## 8. 交付要求

下一位 Agent 每个里程碑都要：

```bash
python -m compileall -q lab
python -m unittest -v lab.test_lab
git diff --check
git status --short
git add <intentional-files>
git commit -m "<focused milestone>"
git push origin arena/01a05b71-yiming
```

报告必须包含：

- 实际执行的命令和结果；
- 实际 seat 数、成功/失败数、reviewer 数、chair 状态；
- private output 路径（不贴私密内容）；
- provenance branch/tip/hash；
- 未验证项、失败原因、费用/调用数限制；
- 没有把模型推断、示例数据或 dry-run 当成真实事实。

## 9. 当前停止点

本交接完成后，当前 Agent 的工作结束。下一 Agent 可以从 Step 1 开始，但必须尊重
上述隐私、预算、branch 和人工确认边界。
