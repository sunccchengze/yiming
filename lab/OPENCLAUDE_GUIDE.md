# OpenClaude 通用指南（安装 · 配置 · 日常用法）

> 这不是圆桌专用文档，而是把 OpenClaude 当成**日常 AI 编程 Agent** 用的完整手册。
> 圆桌只是它的用途之一。读完这份你就能自己给它布置任务。
>
> 官方仓库：https://github.com/Gitlawb/openclaude （"runs anywhere, uses anything"）
> 安装包：npm `@gitlawb/openclaude`。License：MIT。

---

## 0. OpenClaude 是什么（一句话）

一个 **Claude Code 风格的终端编程 Agent CLI**，但**不绑定 Anthropic**——能接
OpenAI 兼容、Gemini、Ollama、GitHub Models、Codex 等几乎所有模型后端。
内置工具：bash、文件读写、grep、glob、agents、MCP、web 搜索、slash 命令、流式输出。

类比：Claude Code 是 Anthropic 官方版；OpenClaude 是开源多后端版。

---

## 1. 安装（一次）

需要 **Node.js ≥ 22**。

```bash
node -v            # 确认 ≥ 22
npm install -g @gitlawb/openclaude@latest
openclaude --version
# 若报 "ripgrep not found"：系统装 ripgrep 并确认 `rg --version` 可用
```

可选：VS Code 扩展（仓库自带 `vscode-extension/`），用于编辑器内聊天、主题。

---

## 2. 配置模型后端（核心前置，一次）

OpenClaude **不自动加载项目 .env**。两种配置方式任选：

### 方式 A：环境变量（临时、推荐先试）

不同后端用不同变量，看下表。**注意 key 只放 shell 环境，别写进仓库/共享文件。**

| 后端 | 触发开关 | 必需变量 | 可选 |
|---|---|---|---|
| **DeepSeek** | `CLAUDE_CODE_USE_OPENAI=1` | `OPENAI_API_KEY` | `OPENAI_BASE_URL=https://api.deepseek.com`、`OPENAI_MODEL=deepseek-chat` |
| **Gemini** | `CLAUDE_CODE_USE_GEMINI=1` | `GEMINI_API_KEY`(或`GOOGLE_API_KEY`) | `GEMINI_MODEL=gemini-3-flash-preview`、`GEMINI_BASE_URL`(默认Google) |
| 任意 OpenAI 兼容 | `CLAUDE_CODE_USE_OPENAI=1` | `OPENAI_API_KEY` | `OPENAI_BASE_URL`、`OPENAI_MODEL`（OpenRouter/Groq/Mistral/LM Studio 都行） |
| Ollama(本地) | `CLAUDE_CODE_USE_OPENAI=1` | — | `OPENAI_BASE_URL=http://localhost:11434/v1`、`OPENAI_MODEL=<模型>` |

### 方式 B：`/provider` 交互配置（推荐，能保存 profile）

```bash
openclaude
# 在会话里输入 /provider，按引导选后端、填 key、存 profile
# 会保存到 ~/.openclaude-profile.json
```

> OpenClaude 用自己独立的配置目录 `~/.openclaude/` 和 `~/.openclaude.json`，
> **不读** `~/.claude` 或项目 `.claude/`。不会动你 Claude Code 的配置。

### 建议：写进你的 shell 启动文件（~/.bashrc 或 ~/.zshrc）

```bash
# ---- DeepSeek（默认）----
export CLAUDE_CODE_USE_OPENAI=1
export OPENAI_BASE_URL="https://api.deepseek.com"
export OPENAI_MODEL="deepseek-chat"
export OPENAI_API_KEY="$DEEPSEEK_API_KEY"   # 你自己 export 过的变量

# 想切 Gemini 时临时注释上面、取消注释下面：
# export CLAUDE_CODE_USE_GEMINI=1
# export GEMINI_MODEL="gemini-3-flash-preview"
# export GEMINI_API_KEY="$GEMINI_KEY"
```

---

## 3. 验证

```bash
echo "用一句话介绍自己" | openclaude --print
```

能返回文字 = 配置成功。

---

## 4. 日常用法（布置任务）

### 4.1 交互式（最常用）

```bash
cd /你的项目目录
openclaude
# 进入对话，直接打字布置任务
```

### 4.2 一次性 / 脚本（print 模式）

```bash
openclaude --print "修复 src/ 里的 bug"
echo "重构这个函数" | openclaude --print
# 输出格式：--output-format text(默认) | json | stream-json
```

### 4.3 后台任务（长任务不占终端）

```bash
openclaude --bg "fix failing tests"            # 后台跑
openclaude --bg --name auth "重构 auth 中间件"
openclaude ps                                   # 查看
openclaude logs auth -f                         # 看日志(实时)
openclaude kill auth                            # 停止
```

### 4.4 续聊 / 分叉

```bash
openclaude --continue                  # 接着最近对话
openclaude --resume <session-id>       # 指定会话
openclaude --continue --fork-session   # 分叉出新会话
```

### 4.5 权限模式

```bash
openclaude --dangerously-skip-permissions   # 自动执行(慎用，仅沙箱)
# 默认模式会逐个问你是否允许某操作（如执行命令、写文件）
```

---

## 5. 内置 slash 命令（会话内输入 `/xxx`）

常用：

| 命令 | 作用 |
|---|---|
| `/provider` | 配置/切换模型后端，保存 profile |
| `/model` | 当前会话换模型 |
| `/clear` | 清空上下文 |
| `/compact` | 压缩长上下文 |
| `/agents` | 查看/配置子 agent |
| `/mcp` | 管理 MCP 服务器（外部工具/数据源）|
| `/permissions` | 配置权限模式 |
| `/cost`、`/stats` | 用量/统计 |
| `/resume`、`/session` | 会话管理 |
| `/help` | 全部命令列表 |
| `/buddy` | 那个像素小人伴侣（娱乐）|
| `/repomap` | 看代码库结构地图 |

进阶：`/model`、`/memory`（长期记忆）、`/skills`（技能）、`/hooks`、`/plan`。

---

## 6. Agents（子代理，可并行拆分任务）

OpenClaude 支持把不同 agent 路由到不同模型（成本优化、按模型强弱分工）：

- 配置在 `~/.openclaude/settings.json` 的 `agentModels` + `agentRouting`
- 内置 agent：`Explore`、`Plan` 等，可按类型路由
- 也可在 agent frontmatter 或环境变量里覆盖

> 圆桌其实就用到了类似"多角色独立"的思路，但圆桌是进程级隔离，这里是 agent 级路由。

---

## 7. MCP（外部工具接入）

OpenClaude 支持 Model Context Protocol，可接外部工具/数据源：

```bash
openclaude --mcp-config /path/to/mcp.json
# 或在会话里 /mcp 管理
```

可接：数据库、文件系统、浏览器、第三方 API 等。

---

## 8. 安全要点

- **key 不写进仓库**：只放 shell 环境或 `~/.openclaude-profile.json`（用户级）。
- OpenClaude 用自己配置目录，**不会读/改你的 Claude Code 凭据**。
- 权限：默认会问是否允许操作；`--dangerously-skip-permissions` 只在可信沙箱用。
- 你看到每次调用生成的独立 session 文件是**正常**的（`~/.openclaude/sessions/*.json`），
  每个 `--print` 调用一个。可定期清理或用 `--no-session-persistence` 关闭落盘。

---

## 9. 把它接进圆桌（已有三个 runner）

圆桌只是 OpenClaude 的一个用途，runner wrapper 在 `lab/examples/`：

| 文件 | 后端 | 说明 |
|---|---|---|
| `runner-openclaude-gemini.sh` | Gemini | 免费 key 可用，最省钱 |
| `runner-openclaude-deepseek.sh` | DeepSeek | 便宜 |
| `runner-claude-deepseek.sh` | 官方 Claude Code→DeepSeek | 需要官方 Claude Code CLI |

用法（以 Gemini 为例）：

```bash
# 前置：装 OpenClaude + 配好 provider（见上）
python -m lab council run --run "$RUN" --execute \
  --runner "$(pwd)/lab/examples/runner-openclaude-gemini.sh" \
  --workers 4 --timeout-seconds 900
```

> 注意：把模型配置写进 `~/.bashrc` 后，这些 wrapper 脚本继承同样环境变量，
> 圆桌就能直接用，无需再单独配。

---

## 10. 一句话速记

```text
装：npm i -g @gitlawb/openclaude@latest
配：CLAUDE_CODE_USE_GEMINI=1 + GEMINI_API_KEY  (或 USE_OPENAI + OPENAI_*)
跑：openclaude                交互
    openclaude --print "任务"  一次性
    openclaude --bg "任务"     后台
续：--continue / --resume
权限：默认确认，--yolo 跳过(慎用)
```
