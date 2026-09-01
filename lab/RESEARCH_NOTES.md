# Council research notes

检索日期：2026-09-01（Asia/Shanghai）。这些链接用于吸收公开架构经验，未复制
任何外部仓库代码；成熟底座仍是 OpenWiki + DeepTutor。

## 采用的模式

### 1. 先独立、后共享

[Agent chat rooms 的公开实践](https://www.mindstudio.ai/blog/agent-chat-rooms-multi-agent-debate-claude-code)
明确区分“同题并行询问”和“互相阅读后对话”，并指出先看到第一个答案会产生
herding/anchoring。Yiming Council 因此把首轮固定为并行独立 pass，之后才构造
blind packet。

### 2. 自定义角色 brief，而不是空泛的 generic agent

[Council skill 的公开说明](https://www.getclaudeskills.com/skills/council-danielmiessler)
强调真正的差异来自每个成员的 name、role、stance 和 push-on，而不是启动多个
没有上下文的通用 agent。这里的角色 brief 直接来自每个书籍/人物的 `SKILL.md`，
并在 prompt 中标记为 bounded reference。

### 3. 结构化生命周期与可审计 run directory

[Senate](https://github.com/SebastianElvis/senate) 的公开架构使用 agenda、独立
turn、transcript、context、state 和 notes 等制品；
[Multi-Agent LLM Debater](https://github.com/mjsushanth/Multi_Agent_LLM_Debater)
使用 opening/rebuttal/closing 与多维 judge。Yiming Council 先采用更克制的
independent pass + blind chair：每个席位的 stdout/stderr、prompt、失败代码和
最终 blind packet 都落盘，后续再增加受限 rebuttal。

### 4. 成本与终止条件是协议的一部分

[公开的多 agent 编排模式总结](https://www.digitalapplied.com/blog/multi-agent-orchestration-5-patterns-that-work)
把 debate/council 的成本描述为随席位和轮次放大的调用量。实现因此显式提供
`--max-seats`、`--workers`、`--timeout-seconds`，默认 12 席，不默认跑满 66 席；
`--execute` 也必须显式提供。

## X 上的补充经验

- [nyk 的讨论](https://x.com/nykdotdev/status/2087778387742130302)把 subagent
  定义成“压缩/扇出”工具，并提醒只有在确实需要跨 agent 协作时才支付 coordination
  tax；这对应本实现的并行首轮与单主席汇总。
- [Walden 的讨论](https://x.com/walden_yan/status/2047054554433462360)强调主循环
  持有状态、worker 尽量无状态；这里因此不让席位共享 memory，而把状态落到可审计
  的 run directory。
- [Josh Rosen 的讨论](https://x.com/JoshARosen/status/2087944178558791874)把递归
  subagent 看成有依赖和错误传播半径的图；这里不默认递归 spawn，且把主席作为唯一
  高影响汇聚节点，配 reviewer 与人工门禁。
- [Akshay 的讨论](https://x.com/akshay_pachaar/status/2035986229687451723)强调
  每个 subagent 应有专门 system prompt、工具和模型偏好；本实现把每个 skill 的
  brief、独立 home 和只读边界绑定在 seat 上。

## 没有采用的做法

- 没有把所有席位的回答提前塞进彼此的 context；那会破坏独立性；
- 没有用“谁的名气更大”替代证据；主席先只接收匿名 proposal；
- 没有把网上未经核验的 benchmark 数字写进决策逻辑；
- 没有复制 Senate、AgentCouncil、CrewAI、AutoGen 或任何其他仓库的代码；
- 没有把 `sun-chengze-perspective` 当作“本人发言器”，只把它当作带明确边界的
  决策校准视角。

## 当前协议的可复现定义

```text
input: question + common factual context + N independent skill lenses
round 1: N isolated DeepTutor CLI processes in parallel
boundary: each process gets only its own lens; one DEEPTUTOR_HOME per seat
normalization: strip seat names into P001 ... PN
review: up to three isolated reviewers inspect evidence, dissent, and actionability
chair: one separate DeepTutor process reads the anonymous packet and review notes
output: recommendation + trade-offs + strongest dissent + evidence gaps + reversible experiment
recovery: completed seat logs are reusable with --resume; failed seats remain explicit
```

## 实现后的审计补强

- roster ID 由 `kind + relative_path + file_sha256` 确定，不依赖枚举顺序；每行同时保存
  Git branch、tip commit、dirty state、文件 hash 和人物 lens disclaimer。
- `isolation-audit.json` 保存每个 seat 的 prompt hash、共同上下文 hash、独立 cwd、
  独立 `DEEPTUTOR_HOME` 和 `peer_output_injected=false`。这证明 adapter 没有把 peer
  文本注入首轮；它不是操作系统级 sandbox，所以工具/provider 的真正权限仍要另行审计。
- 原始输出先留在 seat 私有目录，再经过身份字符串去标识才进入 `blind-packet.json`；
  P### 到真实 seat 的映射单独放在 `blind-map.json`，不会传给 reviewer 或 chair。
- ballot 使用明确权重但不把缺字段补成 0；`decision-record.json` 和
  `quality-gates.json` 把解析失败、少数意见、证据缺口和人工门禁保留为可检查状态。
- retry 不是默认行为。`--max-attempts` 和 `--max-calls` 都写入 run manifest；每个
  attempt 独立保存 stdout/stderr/状态，`--resume` 只复用成功 seat 的 stdout。
