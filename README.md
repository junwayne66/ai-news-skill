# AI News Skill

Horizon 风格 + Loop Engineering 的每日 AI 行业新闻 skill。支持 **OpenClaw**（编排）、**Hermes**（执行）、**Claude / Cursor / Codex**（独立或开发环境）等多平台，核心数据流参考 [Horizon](https://github.com/Thysrael/Horizon)，治理层（审批、归档、发布）为本 skill 扩展。

如果希望让 OpenClaw 智能体自己按步骤安装和验证本 skill，请让它优先阅读 [OPENCLAW_AGENT_RUNBOOK.md](OPENCLAW_AGENT_RUNBOOK.md)。

## 核心架构

```text
Schedule → RunContext + loop_state.json
        → Horizon 管线: fetch → dedupe → score → filter → enrich → draft
        → Maker-checker review → 飞书审批 → 多维表归档 → 卡片发布
```

| 思想来源 | 在本 skill 中的体现 |
| --- | --- |
| Horizon | 多源采集、URL/主题去重、AI 评分、分类配额、背景 enrichment |
| Loop Engineering | 持久化 `loop_state.json`、可验证终止条件、迭代上限、maker-checker |
| OpenClaw | Cron 调度、skill 安装、飞书连接器、隔离会话 |
| Hermes | 可选执行器，负责重复性 fetch/rank/enrich 子循环 |
| Claude/Cursor | `/loop`、Task 子 agent、云端 agent 运行同一套契约 |

核心原则：

- **确定性阶段用脚本**：`normalize_run_context`、`loop_state`、`validate_news_payload`、hash、飞书 API。
- **不确定性阶段用 agent/subagent**：新闻发现、可信度、排序、 enrichment、中文编辑、驳回重规划。
- **编排器**负责读写信令状态、分派子 agent、审批门禁；**Hermes** 仅执行有界切片，不直接发布。
- 记忆通过 `scripts/query_memory.py` 按需加载，不把全部参考文档塞进上下文。

官方参考：

- Horizon: https://github.com/Thysrael/Horizon
- OpenClaw Skills: https://docs.openclaw.ai/cli/skills
- OpenClaw Cron: https://docs.openclaw.ai/cli/cron
- Lark/Feishu CLI: https://github.com/larksuite/cli

## 目录结构

```text
ai-news/
├── SKILL.md
├── data/
│   ├── config.example.json      # Horizon 风格源/过滤/loop 配置
│   └── runs/<job_id>/loop_state.json
├── agents/
│   └── openai.yaml
├── references/
│   ├── architecture.md
│   ├── horizon-pipeline.md      # Horizon 数据流映射
│   ├── loop-engineering.md      # Loop 设计原则
│   ├── platform-adapters.md     # OpenClaw/Hermes/Claude 适配
│   ├── feishu-workflow.md
│   ├── memory-index.md
│   ├── openclaw-lark-cli-quickstart.md
│   ├── openclaw-runtime.md
│   ├── script-boundaries.md
│   └── subagent-contracts.md
└── scripts/
    ├── loop_state.py            # 持久化 loop 状态
    ├── archive_feishu_base.py
    ├── build_feishu_card.py
    ├── fetch_feishu_base_records.py
    ├── fetch_hackernews.py
    ├── fetch_rss.py
    ├── fetch_sources.py           # 编排确定性采集（RSS + HN）
    ├── url_dedupe.py              # URL 级跨源去重
    ├── hash_payload.py
    ├── normalize_run_context.py   # 多平台 RunContext
    ├── query_memory.py
    ├── send_feishu_approval.py
    ├── send_feishu_card.py
    ├── send_feishu_message.py
    ├── validate_feishu_callback.py
    └── validate_news_payload.py
```

## 前置依赖

### OpenClaw

OpenClaw 需要已经安装并可用：

```bash
openclaw --help
openclaw skills --help
openclaw cron --help
```

OpenClaw 官方支持从本地目录安装 skill；本地目录根部必须包含 `SKILL.md`。

### Python

脚本使用 Python 标准库，建议 Python 3.9+：

```bash
python3 --version
```

### lark-cli / feishu-cli

本 skill 的飞书能力通过官方 `larksuite/cli` 实现。官方命令名通常是 `lark-cli`。如果你的 OpenClaw 机器上安装的命令名是 `feishu-cli`，请设置：

```bash
export LARK_CLI_BIN=feishu-cli
```

如果命令名是官方默认值，则无需设置：

```bash
export LARK_CLI_BIN=lark-cli
```

检查 CLI 是否可用：

```bash
$LARK_CLI_BIN --help
$LARK_CLI_BIN auth status
```

如果还未配置，参考官方方式安装和登录：

```bash
npx @larksuite/cli@latest install
lark-cli config init
lark-cli auth login --recommend
lark-cli auth status
```

### 飞书权限和 ID

需要提前准备：

- 新闻管理员 ID：`FEISHU_NEWS_ADMIN_ID`，建议使用 `open_id`。
- 管理员 ID 类型：`FEISHU_NEWS_ADMIN_ID_TYPE`，例如 `open_id`、`user_id`。
- 目标群聊 ID：`FEISHU_GROUP_CHAT_ID`，通常形如 `oc_xxx`。
- 飞书多维表 app token：`FEISHU_BASE_APP_TOKEN`。
- 飞书多维表 table ID：`FEISHU_BASE_TABLE_ID`。
- 飞书应用或登录身份具备消息发送和多维表记录写入权限。
- 如果使用 bot 身份发送群消息，bot 需要已经加入目标群聊。

建议先用 dry-run 验证消息能力：

```bash
$LARK_CLI_BIN im +messages-send \
  --as bot \
  --chat-id "oc_xxx" \
  --text "AI News skill connectivity test" \
  --dry-run
```

### 新闻源能力

OpenClaw 运行环境需要至少一种新闻采集能力：

- 可访问公网网页和官方新闻源。
- 或配置搜索 API/RSS 源。
- 或由 OpenClaw 提供网页搜索/浏览工具。

新闻采集是不确定性任务，由 subagent 判断；但 URL、日期窗口、字段完整性、payload hash 等由脚本做确定性校验。

## 安装 Skill

### 1. 将项目放到 OpenClaw 机器

示例：

```bash
scp -r /path/to/ai-news user@openclaw-host:/opt/skills/ai-news
```

进入 OpenClaw 机器：

```bash
ssh user@openclaw-host
cd /opt/skills/ai-news
```

确认根目录有 `SKILL.md`：

```bash
test -f SKILL.md && echo "SKILL.md found"
```

### 2. 设置脚本权限

```bash
chmod +x scripts/*.py
```

### 3. 安装到 OpenClaw

安装为当前环境可用 skill：

```bash
openclaw skills install /opt/skills/ai-news --as ai-news --force
openclaw skills check
openclaw skills info ai-news
```

只绑定到某个 agent，例如 `ops`：

```bash
openclaw skills install /opt/skills/ai-news --as ai-news --agent ops --force
openclaw skills check --agent ops
openclaw skills info ai-news --agent ops
```

全局安装：

```bash
openclaw skills install /opt/skills/ai-news --as ai-news --global --force
openclaw skills check
```

查看是否安装成功：

```bash
openclaw skills list
openclaw skills list --agent ops
```

## 配置运行环境

最小环境变量：

```bash
export AI_NEWS_PLATFORM=openclaw   # openclaw|hermes|claude|cursor|codex
export AI_NEWS_EXECUTOR=openclaw     # 可选；Hermes 执行切片时设为 hermes
export AI_NEWS_CONFIG=data/config.json
export AI_NEWS_TIMEZONE=Asia/Shanghai
export AI_NEWS_WINDOW=24h
export AI_NEWS_MAX_ITEMS=8
export AI_NEWS_LANGUAGE=zh-CN

export FEISHU_NEWS_ADMIN_ID="ou_xxx"
export FEISHU_NEWS_ADMIN_ID_TYPE="open_id"
export FEISHU_GROUP_CHAT_ID="oc_xxx"
export FEISHU_BASE_APP_TOKEN="base_xxx"
export FEISHU_BASE_TABLE_ID="tbl_xxx"

export LARK_CLI_AS=bot
export LARK_CLI_BIN=lark-cli
```

如果你的命令名是 `feishu-cli`：

```bash
export LARK_CLI_BIN=feishu-cli
```

请把这些变量放到 OpenClaw agent runtime、secret manager、cron wrapper 或服务启动环境中。不要把飞书密钥、token 或管理员私密信息写入 prompt。

## 本地脚本测试

以下测试建议在 OpenClaw 机器上执行。

### 1. 检查 RunContext 归一化（多平台）

```bash
export AI_NEWS_PLATFORM=openclaw  # 或 claude / cursor / hermes
```

缺少必填字段时应返回错误：

```bash
cd /opt/skills/ai-news
scripts/normalize_run_context.py
```

配置变量后应返回 `ok: true`：

```bash
export FEISHU_NEWS_ADMIN_ID="ou_xxx"
export FEISHU_GROUP_CHAT_ID="oc_xxx"
export FEISHU_BASE_APP_TOKEN="base_xxx"
export FEISHU_BASE_TABLE_ID="tbl_xxx"

scripts/normalize_run_context.py
```

### 1b. 检查 Loop State

```bash
scripts/loop_state.py init --job-id ai-news-test --platform openclaw --force
printf '%s\n' '{"stage":"fetching","candidate_count":12}' | scripts/loop_state.py write --job-id ai-news-test
scripts/loop_state.py read --job-id ai-news-test
```

### 2. 检查按需记忆查询

```bash
scripts/query_memory.py \
  --query "subagent peer request memory" \
  --top-k 3 \
  --max-chars 800
```

预期返回 `SKILL.md` 或 `references/subagent-contracts.md` 中的相关小片段。

### 2b. 检查 Horizon 风格确定性采集脚本

RSS 采集（从 config 的 `sources.rss` 读取）：

```bash
python3 scripts/fetch_rss.py --input data/config.example.json --hours 24
```

Hacker News 采集：

```bash
python3 scripts/fetch_hackernews.py --hours 24 --fetch-top-stories 20 --min-score 50
```

返回结果包含统一字段：`id/source_type/headline/url/published_at/metadata`，可直接作为后续去重和评分输入。

### 2c. 检查脚本优先采集编排（推荐主路径）

```bash
cat > /tmp/run-context.json <<'JSON'
{
  "run_context": {
    "job_id": "ai-news-test",
    "window_start": "2026-06-16T09:00:00+08:00",
    "window_end": "2026-06-17T09:00:00+08:00"
  }
}
JSON

python3 scripts/fetch_sources.py \
  --config data/config.example.json \
  --input /tmp/run-context.json \
  --include-collector-candidates \
  > /tmp/prefetched.json

python3 scripts/url_dedupe.py --input /tmp/prefetched.json > /tmp/prefetched-deduped.json
```

然后将 `/tmp/prefetched-deduped.json` 中的 `items` / `collector_candidates` 传给 `source_collector`，由其只补充 `official` / `search` 等非确定性来源。

### 3. 检查 payload hash

```bash
printf '%s\n' '{"title":"AI News","items":[{"headline":"test"}]}' \
  | scripts/hash_payload.py
```

预期返回稳定的 `sha256`。

### 4. 检查新闻 payload 校验

```bash
cat > /tmp/ai-news-payload.json <<'JSON'
{
  "report_date": "2026-06-07",
  "timezone": "Asia/Shanghai",
  "window_start": "2026-06-06T09:00:00+08:00",
  "window_end": "2026-06-07T09:00:00+08:00",
  "items": [
    {
      "headline": "Test AI news",
      "summary": "A concise verified summary.",
      "primary_source_url": "https://example.com/news",
      "published_at": "2026-06-07T08:00:00+08:00",
      "confidence": "high"
    }
  ]
}
JSON

scripts/validate_news_payload.py /tmp/ai-news-payload.json --min-items 1 --max-items 8
```

预期返回：

```json
{"errors": [], "item_count": 1, "ok": true, "warnings": []}
```

### 5. dry-run 测试飞书消息

```bash
printf '%s\n' '{
  "receive_id_type": "chat_id",
  "receive_id": "oc_xxx",
  "text": "AI News dry-run test",
  "dry_run": true
}' | scripts/send_feishu_message.py
```

如果你的飞书 CLI 命令名是 `feishu-cli`：

```bash
printf '%s\n' '{
  "receive_id_type": "chat_id",
  "receive_id": "oc_xxx",
  "text": "AI News dry-run test",
  "dry_run": true
}' | LARK_CLI_BIN=feishu-cli scripts/send_feishu_message.py
```

### 6. dry-run 测试多维表写入

```bash
printf '%s\n' '{
  "records": [
    {
      "fields": {
        "日期": "2026-06-07",
        "标题": "AI News dry-run",
        "摘要": "dry-run archive record",
        "Run ID": "ai-news-test"
      }
    }
  ]
}' | scripts/archive_feishu_base.py --dry-run
```

### 7. dry-run 测试多维表记录读回

```bash
printf '%s\n' '{
  "record_ids": ["rec_test"]
}' | scripts/fetch_feishu_base_records.py --dry-run
```

### 8. 基于读回字段构建飞书卡片

```bash
cat > /tmp/ai-news-archived-records.json <<'JSON'
{
  "run_context": {
    "job_id": "ai-news-test",
    "window_start": "2026-06-08T09:00:00+08:00",
    "window_end": "2026-06-09T09:00:00+08:00",
    "timezone": "Asia/Shanghai"
  },
  "results": [
    {
      "record_id": "rec_test",
      "fields": {
        "日期": "2026-06-09",
        "标题": "AI News dry-run",
        "摘要": "dry-run archive record",
        "意义": "验证卡片从多维表字段生成",
        "来源": "https://example.com/news",
        "可信度": "high",
        "分类": "model",
        "Run ID": "ai-news-test"
      }
    }
  ]
}
JSON

scripts/build_feishu_card.py /tmp/ai-news-archived-records.json > /tmp/ai-news-card.json
cat /tmp/ai-news-card.json
```

生产运行时建议使用 `scripts/fetch_feishu_base_records.py` 的真实返回作为 `scripts/build_feishu_card.py` 输入；上面的样例只是本地构建测试。

### 9. dry-run 测试飞书卡片发送

```bash
python3 - <<'PY' >/tmp/ai-news-card-message.json
import json
card_payload = json.load(open("/tmp/ai-news-card.json", encoding="utf-8"))
print(json.dumps({
    "receive_id_type": "chat_id",
    "receive_id": "oc_xxx",
    "card": card_payload["card"],
    "dry_run": True,
}, ensure_ascii=False))
PY

scripts/send_feishu_card.py --input /tmp/ai-news-card-message.json
```

### 10. dry-run 测试飞书互动卡审批发送

```bash
cat > /tmp/ai-news-approval.json <<'JSON'
{
  "job_id": "ai-news-test",
  "payload_hash": "abc123",
  "report_date": "2026-06-09",
  "window_start": "2026-06-08T09:00:00+08:00",
  "window_end": "2026-06-09T09:00:00+08:00",
  "timezone": "Asia/Shanghai",
  "draft_payload": {
    "items": [
      {"headline": "AI News dry-run headline"}
    ]
  },
  "receive_id": "ou_xxx",
  "receive_id_type": "open_id",
  "dry_run": true
}
JSON

python3 scripts/send_feishu_approval.py --input /tmp/ai-news-approval.json --dry-run
```

### 11. 测试飞书审批 callback 校验

先构造 callback body：

```bash
cat > /tmp/ai-news-callback.json <<'JSON'
{
  "decision": "approved",
  "job_id": "ai-news-test",
  "payload_hash": "abc123",
  "operator_user_id": "ou_xxx",
  "expires_at": "2099-01-01T00:00:00+00:00",
  "decided_at": "2026-06-09T10:00:00+08:00"
}
JSON
```

如果先不接入真实 header 签名，可跳过签名检查：

```bash
python3 scripts/validate_feishu_callback.py \
  --input /tmp/ai-news-callback.json \
  --expected-job-id ai-news-test \
  --expected-payload-hash abc123 \
  --admin-id ou_xxx \
  --skip-signature-check
```

接入真实事件时，再补 `--header-timestamp`、`--header-nonce`、`--header-signature` 和 `--app-secret` 做完整签名校验。

## 手动运行 Skill

可以先让 OpenClaw 手动跑一次，不创建定时任务：

```bash
openclaw agent --agent ops \
  --message 'Use $ai-news to run a dry-run daily AI news workflow for the previous 24 hours. Validate scripts and prepare the Feishu approval draft, but do not publish to the group.'
```

如果你的 OpenClaw 版本使用不同的 agent 命令，请用：

```bash
openclaw agent --help
```

或直接在 OpenClaw 对应 agent 会话里发送：

```text
Use $ai-news to run a dry-run daily AI news workflow for the previous 24 hours. Validate scripts and prepare the Feishu approval draft, but do not publish to the group.
```

## 创建每日定时任务

OpenClaw cron 的命令格式是 schedule 在前、prompt 在后。建议使用独立会话，避免继承旧上下文：

```bash
openclaw cron create "0 9 * * *" \
  'Use $ai-news to run the Horizon-style daily AI news loop. Persist loop_state.json, use scripts for deterministic stages, atomic subagents for fetch/score/enrich/draft/review. Stop at approval until admin confirms payload_hash. Archive to Feishu Base before publish.' \
  --name "AI News Daily" \
  --agent ops \
  --session isolated \
  --no-deliver
```

注意：

- prompt 使用单引号，避免 shell 把 `$ai-news` 当环境变量展开。
- `--session isolated` 为每次运行创建独立上下文。
- `--no-deliver` 禁用 OpenClaw runner 的兜底投递；最终消息由本 skill 调用飞书脚本发送。

查看任务：

```bash
openclaw cron list --agent ops
openclaw cron show <job-id>
```

手动触发并等待：

```bash
openclaw cron run <job-id> --wait --wait-timeout 30m
```

查看运行记录：

```bash
openclaw cron runs --id <job-id> --limit 10
```

## 审批流程

### MVP：私聊审批

最快可用版本使用飞书私聊审批：

1. 主 agent 生成日报草稿。
2. `scripts/validate_news_payload.py` 做确定性校验。
3. `scripts/hash_payload.py` 计算 `payload_hash`。
4. `scripts/send_feishu_message.py` 将草稿和 `payload_hash` 发给新闻管理员。
5. 管理员回复：

```text
同意发布 <payload_hash>
```

或：

```text
驳回 <反馈内容>
```

6. 主 agent 校验 hash。
7. 同意后调用 `archive_record_builder` 准备多维表字段。
8. 调用 `scripts/archive_feishu_base.py` 写入多维表。
9. 调用 `scripts/fetch_feishu_base_records.py` 读回已归档记录。
10. 调用 `scripts/build_feishu_card.py` 基于读回字段组装飞书卡片。
11. 调用 `scripts/send_feishu_card.py` 将卡片发送到群聊。
12. 驳回后主 agent 根据反馈调用 `replan_advisor`，只重跑必要 subagent。

### 进阶：互动卡审批

当前已提供两个确定性脚本：

- `scripts/send_feishu_approval.py`
- `scripts/validate_feishu_callback.py`

互动卡 callback 的签名、操作者 ID、过期时间、payload hash 必须由脚本校验，不能由 LLM 自行判断。

## 真实发送前检查清单

发布到真实群聊前，至少完成：

```bash
openclaw skills check --agent ops
$LARK_CLI_BIN auth status
scripts/normalize_run_context.py
scripts/query_memory.py --query "quality gates source duplicate confidence"
scripts/validate_news_payload.py /tmp/ai-news-payload.json --min-items 1 --max-items 8
scripts/send_feishu_message.py --receive-id "oc_xxx" --receive-id-type chat_id --text "AI News live connectivity test" --dry-run
scripts/archive_feishu_base.py --dry-run < /tmp/ai-news-base-records.json
scripts/fetch_feishu_base_records.py --dry-run < /tmp/ai-news-archive-result.json
scripts/build_feishu_card.py /tmp/ai-news-archived-records.json > /tmp/ai-news-card.json
scripts/send_feishu_card.py --input /tmp/ai-news-card-message.json --dry-run
```

确认 dry-run 输出正常后，再去掉 `dry_run` 或 `--dry-run`。

## 多维表字段建议

目标表建议至少包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `日期` | Date | 日报日期 |
| `标题` | Text | 新闻标题 |
| `摘要` | Text | 新闻摘要 |
| `意义` | Text | 为什么重要 |
| `分类` | Single select | model/product/funding/policy/research/infra/enterprise/security/other |
| `地区` | Single select | global/china/us/eu/other |
| `来源` | URL 或 Text | 主来源和辅助来源 |
| `发布时间` | DateTime | 来源发布时间 |
| `可信度` | Single select | high/medium/low |
| `影响分` | Number | 1-5 |
| `新颖度` | Number | 1-5 |
| `实体` | Text 或 Multi-select | 公司、实验室、产品等 |
| `Run ID` | Text | `job_id` |
| `审批状态` | Single select | approved/rejected/failed |
| `飞书消息 ID` | Text | 群消息 ID |
| `归档时间` | DateTime | 写入时间 |

字段名需要和 `archive_record_builder` 返回的 `fields` 对齐。

## 常见问题

### OpenClaw 找不到 skill

检查安装路径根部是否有 `SKILL.md`：

```bash
ls /opt/skills/ai-news/SKILL.md
openclaw skills list
openclaw skills info ai-news
```

如果只安装到了某个 agent，需要加 `--agent` 检查：

```bash
openclaw skills check --agent ops
openclaw skills info ai-news --agent ops
```

### `$ai-news` 在 cron prompt 中消失

这是 shell 展开导致的。使用单引号：

```bash
'Use $ai-news to run ...'
```

或者转义：

```bash
"Use \$ai-news to run ..."
```

### `lark-cli` 不存在

如果机器上命令名是 `feishu-cli`：

```bash
export LARK_CLI_BIN=feishu-cli
```

如果未安装，参考官方安装：

```bash
npx @larksuite/cli@latest install
```

### 飞书发送失败

先 dry-run：

```bash
$LARK_CLI_BIN im +messages-send --as bot --chat-id "oc_xxx" --text "test" --dry-run
```

再检查：

- `lark-cli auth status` 是否成功。
- bot 是否加入目标群。
- `FEISHU_GROUP_CHAT_ID` 是否是正确群 ID。
- 当前身份是否有消息发送权限。
- OpenClaw 运行环境是否继承了 `LARK_CLI_BIN`、`LARK_CLI_AS` 和飞书相关变量。

### 多维表写入失败

检查：

- `FEISHU_BASE_APP_TOKEN` 是否正确。
- `FEISHU_BASE_TABLE_ID` 是否正确。
- 表字段名是否和写入 payload 一致。
- 当前飞书身份是否有 Base 写入权限。
- 先运行 `scripts/archive_feishu_base.py --dry-run`。

### 新闻质量不稳定

优先调整 subagent 输入，而不是放宽脚本校验：

- 增加可靠新闻源。
- 调整 `AI_NEWS_MAX_ITEMS`。
- 在 prompt 中指定更明确的目标受众。
- 保持 `quality_reviewer` 严格；宁可少发，也不要发布证据不足的新闻。

## 更新 Skill

修改本目录后重新安装：

```bash
openclaw skills install /opt/skills/ai-news --as ai-news --agent ops --force
openclaw skills check --agent ops
```

如果是全局安装：

```bash
openclaw skills install /opt/skills/ai-news --as ai-news --global --force
openclaw skills check
```

## 安全建议

- 不要把飞书 app secret、tenant token、用户 token 写进 prompt 或 README。
- 使用 OpenClaw secret manager 或系统环境变量管理敏感信息。
- 对真实群聊发送前必须先 dry-run。
- 发布动作必须匹配管理员审批过的 `payload_hash`。
- 多维表写入失败不能触发重复群发，只能重试归档。
- 管理员驳回后只能重做必要步骤，避免整条链路无意义重复。
