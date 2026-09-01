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
