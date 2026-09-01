# Yiming Lab 阶段检查点与待确认计划

- 检查点日期：2026-09-01（Asia/Shanghai）
- 当前分支：`arena/01a05b71-yiming`
- 当前 HEAD：`f1e87a7 Add council provenance ballots and quality gates`
- 状态：**等待用户确认后再进入下一阶段**

> 本文件是阶段性留档，不是新的产品方向批准书。下一阶段不会在用户确认前执行模型调用、读取新的私有语料或安装到用户 Agent 目录。

## 一、已经完成的阶段

### 1. 基础事实源

- 盘点了 `sunccchengze` 账号可见的近期项目、全部 branch 和近期 commit；已有本地 inventory 作为事实输入。
- 保留了 branch/commit 信号，不只看默认 `main`。
- 采集器默认过滤 `.env`、私钥、凭据、疑似 token、二进制、大型依赖和构建产物，同时保留 `.github` 文本、工作流和规则文件。
- Atlas 原型仍保留为项目轨迹/知识源适配器，不再继续作为孤立展示站堆叠 UI。

### 2. 已推送的 Yiming Council 适配层

现有实现已经不是空计划，而是一个可准备、可 dry-run、可恢复的薄适配层：

- `lab/council.py`
  - 从本地 `-SKILL-` checkout 只读发现 `SKILL.md`；
  - 将蒸馏书籍、人物 perspective 和方法 skill 变成稳定 seat；
  - seat ID 基于 `kind + relative_path + file_sha256`，不依赖枚举顺序；
  - 记录 source branch、tip commit、dirty state、文件 hash 和“分析镜而非真人发言”的边界。
- `lab/council_protocol.py`
  - 第一轮独立并行 seat；
  - 每个 seat 使用独立 `DEEPTUTOR_HOME` 和独立运行目录；
  - 第一轮完成后才生成匿名 `blind-packet.json`；
  - blind reviewers 只看匿名提案，不看真实 seat 映射；
  - chair 在最后读取匿名提案、review、ballot 和证据缺口；
  - 支持 `--resume`，成功 seat 的 stdout 可复用，失败 seat 保留失败记录；
  - 明确的 `--max-seats`、`--workers`、`--timeout-seconds`、`--max-attempts`、`--max-calls`。
- `lab/council_records.py`
  - 解析结构化 ballot、review 和 chair memo；
  - 缺字段不补成 0，不把缺失当作反对；
  - 生成 `decision-record.json`、`quality-gates.json` 和 `DISSENT_LEDGER.md`。
- `lab/pipeline.py`
  - 生成本地项目事实包、OpenWiki local-git 配置和 DeepTutor 运行计划；
  - 默认禁止把私有制品写进当前 Git checkout；
  - `--execute` 不是默认行为。
- `lab/routing.py` / `lab/skills.py`
  - 以 `universal-skill-router` 为协调入口；
  - 按任务选择 DeepTutor capability、工具、证据门禁和 `sun-chengze-perspective`；
  - 只读取最小 skill 组，不把整个 skill 仓库塞进上下文。

### 3. 已吸收的成熟项目和公开经验

当前方案的核心不是从零写一个新 council，而是组合已有项目：

| 来源 | 已确认事实 | 当前用法 |
|---|---|---|
| [Council of High Intelligence](https://github.com/0xNyk/council-of-high-intelligence) | MIT；当前固定上游 commit `502ceda82050d607cbef88078a69b07084835410`；18 个历史人物 lens；支持 full/triad/duo、provider routing、blind/weighted verdict 等协议 | 借鉴并对齐独立席位、匿名审查、dissent、预算和 provider 边界；不盲目复制整仓 |
| [Karpathy llm-council](https://github.com/karpathy/llm-council) | 三阶段范式：并行独立回答、匿名互评、主席综合；GitHub API 当前未给出可确认的 license 信息 | 只吸收公开方法论；未作为代码依赖 |
| [Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) | orchestrator-worker、独立 context、并行研究、外部记忆和独立 citation pass | 借鉴“先独立、后汇聚”和外部制品；不把性能数字直接当成本项目保证 |
| [OpenWiki](https://github.com/langchain-ai/openwiki) | npm `0.3.2`；Node `>=22`；MIT；personal/code wiki、local git connector、Markdown/OKF 输出 | 作为个人/项目知识底座；Yiming 只生成配置和运行计划 |
| [DeepTutor](https://github.com/HKUDS/DeepTutor) | PyPI `1.6.2`；Python `>=3.11,<3.14`；Apache-2.0；支持 `run`、KB、research、question、visualize、memory | 作为每个独立 seat 的 CLI runtime 和最后 chair/reviewer runtime |
| 用户 `[-SKILL-](https://github.com/sunccchengze/-SKILL-)` | `arena/01a048e7-skill@4cbe659` 含 OpenWiki、DeepTutor skill、router、research workflow、quality gates；`main@0da485b45aad600fe98e7316885a094ea508cfaa` 含当前 `sun-chengze-perspective` | 作为 seat catalog、个人校准镜和人工质量门；不把 branch 差异伪装成单一 snapshot |

已保存的详细外部检索记录见 [`RESEARCH_NOTES.md`](RESEARCH_NOTES.md)。

### 4. 当前已经推送的 commit 链

```text
9b5e694 Add independent skill council adapter
 d217134 Add blind reviewers and resumable council runs
 ab70eb2 Document subagent design sources
 f1e87a7 Add council provenance ballots and quality gates
```

之前的 Atlas 里程碑也在同一 branch 上。当前已将本地 checkout 对齐到远端的
`f1e87a7`，避免把已完成工作误判成未开始。

## 二、当前验证结果

已在 `f1e87a7` 上重新执行：

```text
python -m compileall -q lab       PASS
python -m unittest -v lab.test_lab PASS — 10 tests
python -m lab --help              PASS
```

已有针对性测试覆盖：

- roster 只发现目标 people/books；
- source branch、tip commit、dirty state 和 hash provenance；
- blind packet 去除 seat 身份且保留私有映射；
- 独立 home、独立 prompt、peer output withheld 审计；
- reviewer/ballot/chair 结构化解析；
- resume 与失败记录；
- 调用预算；
- private output 在 checkout 内的拒绝；
- 无 key preparation/dry-run 不执行模型。

## 三、你提出的新想法如何落地

你的想法是：把 `-SKILL-` 中蒸馏过的人和书变成独立 subagent，举行盛大的百人圆桌。
当前实现将它拆成四个层次：

```text
人物/书籍 SKILL.md
        ↓ 只读发现 + provenance + 稳定 seat ID
独立 seat pass
        ↓ 每个 seat 只收到共同问题 + 共同事实 + 自己的 lens
匿名 reviewer pass
        ↓ 只看 P001...PN 的匿名提案，不知道真实姓名
Chair pass
        ↓ 汇总共识、分歧、证据缺口、可逆实验和停止条件
```

重要的语义边界：

- seat 是某个方法/人物/书籍的**分析镜**，不是该真人本人，也不是书作者的授权代言；
- 同一个模型的多个 seat 可以有认知角度差异，但不能冒充跨模型、跨文化或真实专家多样性；
- “百人”支持作为显式大规模模式，但不默认打开；第一次应从 5 或 12 席开始；
- 首轮故意不让 seat 互相聊天，避免第一个回答造成 anchoring/herding；
- “共享上下文”只能是用户批准的事实包，不能偷偷包含其他 seat 的回答或私有映射。

## 四、等待确认的下一阶段计划

### Phase A：确认 roster 与隐私范围

1. 在用户提供/允许的两个本地 `-SKILL-` checkout 上重新运行 `council roster`；
2. 核对预期的 people-books roster（当前文档记录为 **66 个 seat：33 本书 + 33 个人物视角**）；
3. 只读取每个目标包的 `SKILL.md`、license/notice 和必要的引用说明；
4. 默认不读取 `memory/`、访谈原文和其他可能含私人细节的 references；
5. 确认是否允许把 `sun-chengze-perspective` 的完整 skill 放进本地 seat brief；它默认只写在 Git checkout 外的私有运行目录。

### Phase B：小规模无 key 验收

1. `council prepare --max-seats 5 --reviewer-count 3`；
2. 检查 prompt、独立 home、blind packet、private map 和质量门；
3. `council run` 默认 dry-run，确认 expected calls、worst-case calls 和错误处理；
4. 用本地 fake DeepTutor executable 做一次端到端协议测试，不调用远程模型；
5. 出具第一份可审阅的 `COUNCIL_PLAN.md` 和制品树。

### Phase C：真实小圆桌

仅在用户确认且 provider 已配置后：

1. 先用 3–5 个 seat 跑真实 `--execute`；
2. 不自动安装到 `~/.claude/agents`，不自动修改用户其他 Agent 配置；
3. 检查每席 stdout/stderr、是否出现 peer leakage、是否按要求输出 ballot；
4. 人工阅读 `DISSENT_LEDGER.md`、`decision-record.json` 和 `quality-gates.json`；
5. 若小规模质量可接受，再扩到 12 席。

### Phase D：百人模式的显式实验

仅在 Phase C 通过后才考虑：

1. `--max-seats 0` 或显式 `--max-seats 66/100`；
2. 强制要求 `--max-calls`、`--workers`、`--timeout-seconds` 和人工确认；
3. 分批执行并保存 checkpoint，不因单个 seat 失败而伪造全体共识；
4. 保留完整 dissent 与 abstain，不把票数当事实正确率；
5. 评估 token、时间和费用后再决定是否常态化；
6. 不默认添加开放式互聊/递归 spawn，除非另做协议和风险评审。

### Phase E：OpenWiki / DeepTutor 知识底座接线

1. 用 OpenWiki 的 local-git connector 连接用户明确指定的本地项目路径；
2. 用项目事实包生成 DeepTutor KB；
3. 将研究章程、证据表、claim-source map 和 council report 都留在本地可审计目录；
4. 通过 OpenWiki wiki 可视化项目关系，通过 DeepTutor 做 research、quiz、mastery path；
5. 仍然保持模型 key、私有源码、个人 memory 和运行输出不进入 Git。

### Phase F：交付门禁

- 运行针对性测试、静态检查和 fake-runtime E2E；
- 做一次独立隐私/许可/依赖审查；
- 记录实际验证项、未验证项和失败原因；
- 每个里程碑单独 commit/push 到 `arena/01a05b71-yiming`；
- 不在用户确认前进入 Phase C、D 或 E 的真实执行部分。

## 五、请你确认的事项

请确认以下默认值，或者直接修改：

1. **第一轮规模**：是否先跑 5 席，再跑 12 席，最后才考虑 66/100 席？
2. **roster 范围**：是否默认只纳入 `people-books`，即蒸馏书籍和人物视角；方法类 skill 只做 reviewer/support，不自动变成席位？
3. **个人语料边界**：是否允许使用完整 `sun-chengze-perspective/SKILL.md` 作为本地 seat brief，但默认不读取 `memory/`、访谈和 references？
4. **执行后端**：是否先以 DeepTutor CLI 作为统一 seat runtime，保留 0xNyk Council/ Karpathy 作为协议来源，而不是现在就安装其他 host 的插件？
5. **真实执行条件**：是否仅在你明确说“确认执行”且 provider 已配置后，才允许任何远程模型调用？

建议确认语句：

> **确认执行 Phase A + Phase B；第一轮 5 席；只读 people-books；允许读取 perspective 的 SKILL.md，不读取 memory/references；真实模型调用另行确认。**

收到确认前，本仓库停在本检查点，不继续扩展实现。
