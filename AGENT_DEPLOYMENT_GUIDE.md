# AI Agent 部署指南：ai-news-skill

> **触发语（给用户 AI Agent 的原话）**
>
> 参考项目 https://github.com/junwayne66/ai-news-skill.git ，安装部署 ai-news-skill

本指南面向 **AI Agent**（OpenClaw / Hermes / 其他可执行 shell 的 agent）。按阶段执行，缺信息时向用户交互式提问，不要臆造 ID、路径或凭据。

## 0. 目标与交付标准

部署完成后，用户应获得：

| 能力 | 说明 |
| --- | --- |
| 工作日日报 | 周一至周五 08:00（`Asia/Shanghai`）自动发送前 24h AI 新闻 |
| 周日周报 | 每周日 20:00 发送本周最热门 AI 新闻汇总 |
| 直接发群 | **无需管理员审批**，内部质检通过后直接发飞书群 |
| 原文链接 | 每条新闻卡片含可点击 `[原文链接](url)` |
| 主题覆盖 | 含具身智能、机器人、世界模型等领域 |

## 1. 检测运行平台

```bash
# OpenClaw
command -v openclaw && openclaw --version

# Hermes
command -v hermes && hermes --version
```

| 检测到 | `AI_NEWS_PLATFORM` | Skill 安装方式 |
| --- | --- | --- |
| OpenClaw | `openclaw` | `openclaw skills install <dir> --as ai-news --agent <id> --force` |
| Hermes | `hermes` | 将 skill 目录放入 Hermes skills 路径并注册（见 Hermes 文档） |
| 两者都有 | 询问用户优先使用哪个 | 按用户选择 |

若都不可用，停止并指导用户安装 OpenClaw 或 Hermes。

## 2. 目录结构约定

优先使用主机公共目录（若存在）：

```text
/home/<user>/.share/skills/ai-news-skill/    # skill 源码
/home/<user>/.share/secrets/botinkit.env       # 可选密钥
/home/<user>/.share/memory/                    # 记忆（若平台使用）
~/.openclaw/skills -> ~/.share/skills          # OpenClaw 常见软链
```

若无 `.share`，使用 `~/ai-news-skill` 或用户指定路径。根目录必须有 `SKILL.md`。

### 2.1 获取源码

```bash
SKILL_DIR="${SKILL_DIR:-$HOME/.share/skills/ai-news-skill}"
mkdir -p "$(dirname "$SKILL_DIR")"
if [ -d "$SKILL_DIR/.git" ]; then
  git -C "$SKILL_DIR" pull
else
  git clone https://github.com/junwayne66/ai-news-skill.git "$SKILL_DIR"
fi
chmod +x "$SKILL_DIR"/scripts/*.py "$SKILL_DIR"/scripts/*.sh
test -f "$SKILL_DIR/SKILL.md"
```

## 3. 向用户收集信息（交互式）

一次问清，缺什么再问什么：

```text
请提供 ai-news-skill 部署信息：
1. 目标平台：OpenClaw 还是 Hermes？
2. Agent ID（OpenClaw 默认 main；若无 main 则列出 openclaw agents list 让用户选）
3. 飞书群 chat_id（oc_xxx）——日报/周报发送目标
4. 飞书多维表 app_token 和 table_id（没有则我可帮你创建）
5. lark-cli 命令名：lark-cli 还是 feishu-cli？
6. 发送身份：bot 还是 user？（默认 bot）
7. skill 安装目录（默认 ~/.share/skills/ai-news-skill）
8. 时区（默认 Asia/Shanghai）
```

**不再需要** `FEISHU_NEWS_ADMIN_ID`（已取消审批）。

## 4. 前置依赖检查

### 4.1 Python

```bash
python3 --version   # 需要 3.9+
```

### 4.2 lark-cli / feishu-cli

```bash
export LARK_CLI_BIN=lark-cli   # 或 feishu-cli
$LARK_CLI_BIN --help
$LARK_CLI_BIN auth status
```

未配置时：

- OpenClaw 主机：`lark-cli config bind --source openclaw --app-id <appId> --identity bot-only`
- 或：`lark-cli config init` + `lark-cli auth login --recommend`
- 确保 `~/.lark-cli/config.json` 可用（可软链到 `~/.lark-cli/openclaw/config.json`）

验证发群 dry-run：

```bash
$LARK_CLI_BIN api POST /open-apis/im/v1/messages \
  --params '{"receive_id_type":"chat_id"}' \
  --data '{"receive_id":"<oc_xxx>","msg_type":"text","content":"{\"text\":\"connectivity test\"}"}' \
  --as bot --dry-run
```

### 4.3 Agent Reach

```bash
pipx install https://github.com/Panniantong/agent-reach/archive/main.zip || \
  python3 -m pip install --user https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
agent-reach doctor --json
```

OpenClaw 需开启 exec：

```bash
openclaw config set tools.profile coding
```

### 4.4 模型（OpenClaw + botinkit 示例）

```bash
openclaw config set agents.main.model botinkit/smart-router
# 复杂子任务在 prompt 中指定 botinkit/deepseek-v4-pro
```

## 5. 环境变量

写入平台持久环境（OpenClaw 推荐 `~/.openclaw/gateway.systemd.env`），并创建 skill 本地引导文件 `$SKILL_DIR/.env.e2e`：

```bash
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"
set -a
source "$HOME/.openclaw/gateway.systemd.env"    # 若存在
source "$HOME/.share/secrets/botinkit.env"      # 若存在
set +a

export AI_NEWS_PLATFORM=openclaw                # 或 hermes
export AI_NEWS_MODE=daily                       # cron 周报任务用 weekly
export AI_NEWS_TIMEZONE=Asia/Shanghai
export AI_NEWS_WINDOW=24h                       # 周报用 7d
export AI_NEWS_MAX_ITEMS=8
export AI_NEWS_LANGUAGE=zh-CN
export AI_NEWS_AGENT_ID=main

export FEISHU_GROUP_CHAT_ID=oc_xxx
export FEISHU_BASE_APP_TOKEN=xxx
export FEISHU_BASE_TABLE_ID=tbl_xxx

export LARK_CLI_BIN=lark-cli
export LARK_CLI_AS=bot
```

验证：

```bash
cd "$SKILL_DIR"
source .env.e2e
scripts/normalize_run_context.py   # 期望 {"ok": true, ...}
```

## 6. 飞书多维表

表字段至少包含：`日期`、`标题`、`摘要`、`意义`、`分类`、`来源`（URL）、`可信度`、`Run ID`。

`来源` 字段必须存 **可点击的原文 URL**（`https://...`），卡片脚本会渲染为 `[原文链接](url)`。

若无现成表，可用 bot 身份创建：

```bash
lark-cli api POST /open-apis/bitable/v1/apps \
  --data '{"name":"AI News Archive"}' --as bot --format json
```

记录返回的 `app_token` 和 `default_table_id`，并按 [references/feishu-workflow.md](references/feishu-workflow.md) 补全字段。

建议将配置写入 `~/.openclaw/ops/ai-news/base.json`：

```json
{
  "name": "AI News Archive",
  "base_token": "<app_token>",
  "tables": { "news_items": "<table_id>" }
}
```

## 7. 安装 Skill

### OpenClaw

```bash
openclaw skills install "$SKILL_DIR" --as ai-news --agent "$AI_NEWS_AGENT_ID" --force
openclaw skills check --agent "$AI_NEWS_AGENT_ID"
openclaw skills info ai-news --agent "$AI_NEWS_AGENT_ID"
```

安装后重启 gateway 使环境变量生效：

```bash
openclaw gateway restart
```

### Hermes

1. 将 `$SKILL_DIR` 放入 Hermes 配置的 skills 目录
2. 在 Hermes 中注册 skill 名称 `ai-news`
3. 确认 Hermes agent 可执行 `scripts/*.py` 且能访问 `lark-cli`

## 8. 创建定时任务

```bash
cd "$SKILL_DIR"
source .env.e2e
bash scripts/setup_schedule.sh
```

等价手动命令：

```bash
# 工作日 08:00 日报
openclaw cron create "0 8 * * 1-5" \
  'Use $ai-news to run the daily AI industry news workflow for the previous 24 hours with AI_NEWS_MODE=daily. Cover embodied intelligence, robotics, and world models. Archive to Base, build card with source links, publish directly to group. No admin approval.' \
  --name "AI News Daily Weekdays" --agent main --session isolated --no-deliver

# 周日 20:00 周报
openclaw cron create "0 20 * * 0" \
  'Use $ai-news to run the weekly AI industry news workflow for the previous 7 days with AI_NEWS_MODE=weekly. Select hottest items. Archive to Base, build weekly card with source links, publish directly to group. No admin approval.' \
  --name "AI News Weekly Sunday" --agent main --session isolated --no-deliver
```

## 9. 端到端验证

```bash
cd "$SKILL_DIR"
source .env.e2e
export AI_NEWS_DIR="$SKILL_DIR"
bash scripts/remote_openclaw_e2e.sh
```

手动跑一次完整生产链路（**无审批，直接发群**）：

```bash
openclaw agent --agent main --timeout 1800 --message \
  'Use $ai-news to run the daily AI industry news workflow for the previous 24 hours with AI_NEWS_MODE=daily. Use botinkit/smart-router for routing and botinkit/deepseek-v4-pro for complex subagents. After internal review, archive, build card with clickable source links, and publish directly to FEISHU_GROUP_CHAT_ID. Do not wait for administrator approval.'
```

### 验收清单

- [ ] `openclaw skills check --agent main` 通过
- [ ] `normalize_run_context.py` 返回 `ok: true`
- [ ] `agent-reach doctor --json` 可用或 `rss_only` 降级可接受
- [ ] 目标群收到 **互动卡片**（非仅文本）
- [ ] 卡片每条新闻有 `[原文链接](url)`
- [ ] 多维表有对应归档记录
- [ ] `openclaw cron list` 含日报和周报两条任务

## 10. 故障排查

| 现象 | 处理 |
| --- | --- |
| Agent 报缺 `FEISHU_*` | 写入 `gateway.systemd.env` 并 `openclaw gateway restart` |
| `lark-cli auth status` 失败 | `config bind --source openclaw` 或重新 login |
| 卡片无链接 | 检查 Base `来源` 字段是否为 `https://` URL |
| 缺机器人/具身智能新闻 | 检查 `config/news_channel_policy.yaml` 中 `robotics`/`embodied_intelligence`/`world_model` |
| cron 未触发 | `openclaw cron list`；确认 gateway 运行中 |
| skill 找不到 | 确认 `SKILL.md` 在安装目录根部；`openclaw skills list` |

## 11. 向用户汇报模板

```text
ai-news-skill 已部署完成。
平台：<openclaw|hermes>
Agent：<agent id>
Skill 路径：<SKILL_DIR>
目标群：<FEISHU_GROUP_CHAT_ID>
多维表：<app_token>/<table_id>
定时任务：
  - 工作日 08:00 日报（AI_NEWS_MODE=daily）
  - 周日 20:00 周报（AI_NEWS_MODE=weekly）
模式：无审批，质检通过后直接发群卡片（含原文链接）
```

## 12. 相关文档

- [SKILL.md](SKILL.md) — 工作流主入口
- [OPENCLAW_AGENT_RUNBOOK.md](OPENCLAW_AGENT_RUNBOOK.md) — OpenClaw 详细 runbook
- [README.md](README.md) — 人工运维手册
- [references/feishu-workflow.md](references/feishu-workflow.md) — 飞书归档与发卡
