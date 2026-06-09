# OpenClaw Agent Runbook: Install And Operate `ai-news`

This document is for an OpenClaw agent. Follow it to install this skill on any OpenClaw instance, ask the user for missing information, validate dependencies, and run the AI News workflow with a main task agent plus atomic subagents.

Authoritative references:

- OpenClaw skills CLI: https://docs.openclaw.ai/cli/skills
- OpenClaw cron CLI: https://docs.openclaw.ai/cli/cron
- Lark/Feishu CLI: https://github.com/larksuite/cli

## Operating Rules For The Agent

1. Do not invent paths, Feishu IDs, app tokens, table IDs, schedules, or credentials.
2. Ask the user for missing information before running commands that require it.
3. Use deterministic scripts for deterministic work:
   - OpenClaw run context normalization.
   - Required field validation.
   - Payload hash and idempotency keys.
   - Feishu message/card sending through `lark-cli` or `feishu-cli`.
   - Feishu Base write and read-back.
   - Feishu card construction from Base record fields.
4. Use the main task agent for orchestration and decisions.
5. Use subagents only for atomic uncertain tasks:
   - News discovery.
   - Source credibility judgment.
   - Deduplication and ranking.
   - Industry impact analysis.
   - Chinese report drafting.
   - Quality review.
   - Replan advice after rejection.
   - Archive record field preparation.
6. Keep context short. Use `scripts/query_memory.py` to load only relevant snippets instead of reading all references into every role.
7. Never publish to the Feishu group before:
   - administrator approval,
   - successful Feishu Base archive,
   - successful read-back from Feishu Base,
   - Feishu card construction from read-back Base fields.

## Required User Inputs

If any of these are unknown, pause and ask the user.

Ask in one concise message:

```text
请提供 ai-news skill 安装所需信息：
1. skill 源目录路径或 Git/repo 获取方式；
2. OpenClaw agent ID（例如 ops），或是否全局安装；
3. 每日运行时间和时区（默认 Asia/Shanghai，09:00）；
4. Feishu CLI 命令名：lark-cli 还是 feishu-cli；
5. 飞书新闻管理员 ID 和 ID 类型（open_id/user_id）；
6. 目标飞书群 chat_id；
7. 飞书多维表 app_token 和 table_id；
8. 新闻源偏好或限制（可选）。
```

Use these variable names internally:

```bash
AI_NEWS_SKILL_DIR="/path/to/ai-news"
AI_NEWS_AGENT_ID="ops"
AI_NEWS_INSTALL_SCOPE="agent" # agent|global|local
AI_NEWS_CRON="0 9 * * *"
AI_NEWS_TIMEZONE="Asia/Shanghai"
LARK_CLI_BIN="lark-cli" # or feishu-cli
LARK_CLI_AS="bot"
FEISHU_NEWS_ADMIN_ID="ou_xxx"
FEISHU_NEWS_ADMIN_ID_TYPE="open_id"
FEISHU_GROUP_CHAT_ID="oc_xxx"
FEISHU_BASE_APP_TOKEN="base_xxx"
FEISHU_BASE_TABLE_ID="tbl_xxx"
```

## Phase 1: Inspect The Target OpenClaw Instance

Run:

```bash
openclaw --help
openclaw skills --help
openclaw cron --help
```

If any command is missing, stop and tell the user:

```text
OpenClaw CLI 在当前实例不可用。请先安装或进入正确的 OpenClaw 运行环境，然后我再继续安装 ai-news skill。
```

Check whether the instance uses `cron create` or an equivalent command:

```bash
openclaw cron create --help
```

If `cron create` is unavailable, inspect:

```bash
openclaw cron --help
openclaw cron add --help
```

Use the equivalent command exposed by this OpenClaw instance. Prefer `cron create "CRON" "MESSAGE"` when available.

## Phase 2: Locate And Validate The Skill Source

If `AI_NEWS_SKILL_DIR` is unknown, ask the user for it.

Check:

```bash
cd "$AI_NEWS_SKILL_DIR"
test -f SKILL.md
test -f agents/openai.yaml
test -d references
test -d scripts
find . -maxdepth 3 -type f | sort
```

Expected important files:

```text
SKILL.md
README.md
OPENCLAW_AGENT_RUNBOOK.md
agents/openai.yaml
references/architecture.md
references/subagent-contracts.md
references/openclaw-runtime.md
references/feishu-workflow.md
references/script-boundaries.md
scripts/normalize_run_context.py
scripts/validate_news_payload.py
scripts/hash_payload.py
scripts/query_memory.py
scripts/archive_feishu_base.py
scripts/fetch_feishu_base_records.py
scripts/build_feishu_card.py
scripts/send_feishu_message.py
scripts/send_feishu_card.py
```

If files are missing, stop and tell the user which files are missing.

Make scripts executable:

```bash
chmod +x scripts/*.py
```

Run local syntax check without generating `__pycache__`:

```bash
python3 - <<'PY'
import ast
from pathlib import Path
files = sorted(Path("scripts").glob("*.py"))
for path in files:
    ast.parse(path.read_text(encoding="utf-8"))
print(f"syntax ok: {len(files)} scripts")
PY
```

## Phase 3: Verify Feishu CLI Dependency

Determine the Feishu CLI binary:

```bash
${LARK_CLI_BIN:-lark-cli} --help
${LARK_CLI_BIN:-lark-cli} auth status
```

If `lark-cli` is missing but the user said `feishu-cli` is installed:

```bash
export LARK_CLI_BIN=feishu-cli
$LARK_CLI_BIN --help
$LARK_CLI_BIN auth status
```

If no CLI works, ask the user to install/configure it:

```text
当前 OpenClaw 实例未找到可用的 lark-cli/feishu-cli，或尚未登录。请先按 larksuite/cli 官方说明安装并完成 auth，然后告诉我继续。
```

Dry-run Feishu message permission:

```bash
$LARK_CLI_BIN im +messages-send \
  --as "$LARK_CLI_AS" \
  --chat-id "$FEISHU_GROUP_CHAT_ID" \
  --text "AI News skill connectivity test" \
  --dry-run
```

If this fails, ask the user to verify:

- bot/user identity has message send permission,
- bot is in the target group,
- `FEISHU_GROUP_CHAT_ID` is correct,
- `LARK_CLI_AS` is correct.

## Phase 4: Export Runtime Environment

Set:

```bash
export AI_NEWS_PLATFORM=openclaw
export AI_NEWS_TIMEZONE="${AI_NEWS_TIMEZONE:-Asia/Shanghai}"
export AI_NEWS_WINDOW="${AI_NEWS_WINDOW:-24h}"
export AI_NEWS_MAX_ITEMS="${AI_NEWS_MAX_ITEMS:-8}"
export AI_NEWS_LANGUAGE="${AI_NEWS_LANGUAGE:-zh-CN}"

export FEISHU_NEWS_ADMIN_ID="$FEISHU_NEWS_ADMIN_ID"
export FEISHU_NEWS_ADMIN_ID_TYPE="${FEISHU_NEWS_ADMIN_ID_TYPE:-open_id}"
export FEISHU_GROUP_CHAT_ID="$FEISHU_GROUP_CHAT_ID"
export FEISHU_BASE_APP_TOKEN="$FEISHU_BASE_APP_TOKEN"
export FEISHU_BASE_TABLE_ID="$FEISHU_BASE_TABLE_ID"

export LARK_CLI_BIN="${LARK_CLI_BIN:-lark-cli}"
export LARK_CLI_AS="${LARK_CLI_AS:-bot}"
```

Validate deterministic context:

```bash
scripts/normalize_run_context.py
```

Expected:

```json
{"ok": true, "run_context": {"platform": "openclaw"}}
```

If missing fields are reported, ask the user only for the missing fields.

## Phase 5: Install The Skill

OpenClaw supports installing from a local directory whose root contains `SKILL.md`.

If installing for one agent:

```bash
openclaw skills install "$AI_NEWS_SKILL_DIR" --as ai-news --agent "$AI_NEWS_AGENT_ID" --force
openclaw skills check --agent "$AI_NEWS_AGENT_ID"
openclaw skills info ai-news --agent "$AI_NEWS_AGENT_ID"
```

If installing globally:

```bash
openclaw skills install "$AI_NEWS_SKILL_DIR" --as ai-news --global --force
openclaw skills check
openclaw skills info ai-news
```

If installing locally without an agent binding:

```bash
openclaw skills install "$AI_NEWS_SKILL_DIR" --as ai-news --force
openclaw skills check
openclaw skills info ai-news
```

If install fails, inspect and report:

```bash
openclaw skills list
openclaw skills list --agent "$AI_NEWS_AGENT_ID"
openclaw skills check --json
```

## Phase 6: Smoke Test Deterministic Scripts

### Memory Query

```bash
scripts/query_memory.py --query "subagent peer request memory" --top-k 3 --max-chars 800
```

### Payload Validation

```bash
cat > /tmp/ai-news-payload.json <<'JSON'
{
  "report_date": "2026-06-09",
  "timezone": "Asia/Shanghai",
  "window_start": "2026-06-08T09:00:00+08:00",
  "window_end": "2026-06-09T09:00:00+08:00",
  "items": [
    {
      "headline": "Test AI news",
      "summary": "A concise verified summary.",
      "primary_source_url": "https://example.com/news",
      "published_at": "2026-06-09T08:00:00+08:00",
      "confidence": "high"
    }
  ]
}
JSON

scripts/validate_news_payload.py /tmp/ai-news-payload.json --min-items 1 --max-items 8
scripts/hash_payload.py /tmp/ai-news-payload.json
```

### Feishu Text Approval Dry-Run

```bash
printf '%s\n' "{
  \"receive_id_type\": \"$FEISHU_NEWS_ADMIN_ID_TYPE\",
  \"receive_id\": \"$FEISHU_NEWS_ADMIN_ID\",
  \"text\": \"AI News approval dry-run\",
  \"dry_run\": true
}" | scripts/send_feishu_message.py
```

### Feishu Base Archive Dry-Run

```bash
cat > /tmp/ai-news-base-records.json <<'JSON'
{
  "records": [
    {
      "fields": {
        "日期": "2026-06-09",
        "标题": "AI News dry-run",
        "摘要": "dry-run archive record",
        "意义": "验证多维表写入字段",
        "来源": "https://example.com/news",
        "可信度": "high",
        "分类": "model",
        "Run ID": "ai-news-test"
      }
    }
  ]
}
JSON

scripts/archive_feishu_base.py --dry-run < /tmp/ai-news-base-records.json
```

### Feishu Base Read-Back Dry-Run

```bash
printf '%s\n' '{"record_ids":["rec_test"]}' \
  | scripts/fetch_feishu_base_records.py --dry-run
```

### Build Feishu Card From Base-Like Fields

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
scripts/hash_payload.py /tmp/ai-news-card.json
```

### Feishu Card Send Dry-Run

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

If dry-run succeeds, the deterministic Feishu execution layer is ready.

## Phase 7: Configure Main Agent And Subagents

Use this operating model:

```text
main_task_agent
  -> source_collector subagent
  -> source_verifier subagent
  -> dedupe_ranker subagent
  -> industry_analyst subagent
  -> report_editor subagent
  -> quality_reviewer subagent
  -> replan_advisor subagent when needed
  -> archive_record_builder subagent after approval
  -> deterministic scripts for archive/read-back/card/publish
```

Before assigning a subagent, query only relevant memory:

```bash
scripts/query_memory.py --query "source verifier quality gates" --top-k 3
scripts/query_memory.py --query "archive record builder fields" --top-k 3
scripts/query_memory.py --query "feishu base archive card publish" --top-k 3
```

If the OpenClaw instance has real subagent tools, spawn separate subagents for each atomic role. If it does not, emulate subagents as isolated labeled passes and preserve the message envelope in `references/subagent-contracts.md`.

Subagents may ask peer questions, but the main agent must route them. Do not pass full run history to every subagent.

## Phase 8: Run A Manual Dry-Run Task

Send this prompt to the target OpenClaw agent:

```text
Use $ai-news to run a dry-run daily AI industry news workflow for the previous 24 hours.
Use the main task agent to decompose work and atomic subagents for uncertain tasks.
Use deterministic scripts for context normalization, validation, hash, Feishu approval notification, Base archive, Base read-back, Feishu card build, and card send.
Prepare the administrator approval draft, but do not send to the group unless approval and Base archive/read-back have succeeded.
If required environment values are missing, ask me for the missing values before continuing.
```

If the OpenClaw CLI supports direct agent messages, use the installed target agent:

```bash
openclaw agent --agent "$AI_NEWS_AGENT_ID" --message 'Use $ai-news to run a dry-run daily AI industry news workflow for the previous 24 hours. Validate deterministic scripts and prepare the Feishu approval draft, but do not publish to the group.'
```

If that command is unavailable, use the OpenClaw UI or the instance's available agent invocation command.

## Phase 9: Create The Daily Cron

Preferred command:

```bash
openclaw cron create "$AI_NEWS_CRON" \
  'Use $ai-news to run the daily AI industry news workflow for the previous 24 hours. Use deterministic scripts for OpenClaw context normalization, Feishu approval notification, Base archive, Base read-back, Feishu card building, and group publishing. Use atomic subagents for uncertain news collection, verification, ranking, editing, and review. If required information is missing, ask the user. Do not publish before administrator approval and Base archive/read-back success.' \
  --name "AI News Daily" \
  --agent "$AI_NEWS_AGENT_ID" \
  --session isolated \
  --no-deliver
```

Important:

- Use single quotes so `$ai-news` is not expanded by the shell.
- Use `--session isolated` to avoid stale context.
- Use `--no-deliver` because the skill sends approved Feishu cards itself.

If this OpenClaw instance uses `cron add` instead of `cron create`, adapt after checking `openclaw cron add --help`. Example shape:

```bash
openclaw cron add \
  --name "AI News Daily" \
  --cron "$AI_NEWS_CRON" \
  --session isolated \
  --no-deliver \
  --message 'Use $ai-news to run the daily AI industry news workflow for the previous 24 hours. Do not publish before administrator approval and Base archive/read-back success.'
```

Verify:

```bash
openclaw cron list --agent "$AI_NEWS_AGENT_ID"
openclaw cron run <job-id> --wait --wait-timeout 30m
openclaw cron runs --id <job-id> --limit 10
```

## Phase 10: Production Workflow The Main Agent Must Enforce

The main task agent must execute this order:

1. Normalize OpenClaw context with `scripts/normalize_run_context.py`.
2. Query memory with `scripts/query_memory.py`.
3. Assign atomic subagents:
   - collect,
   - verify,
   - dedupe/rank,
   - analyze,
   - edit,
   - review.
4. Validate the final draft with `scripts/validate_news_payload.py`.
5. Compute approval payload hash with `scripts/hash_payload.py`.
6. Ask Feishu administrator for approval.
7. If rejected:
   - call `replan_advisor`,
   - rerun only necessary subagents,
   - repeat approval.
8. If approved:
   - call `archive_record_builder`,
   - write Base records with `scripts/archive_feishu_base.py`,
   - fetch written records with `scripts/fetch_feishu_base_records.py`,
   - build card with `scripts/build_feishu_card.py`,
   - compute card hash with `scripts/hash_payload.py`,
   - send card with `scripts/send_feishu_card.py`.
9. Record message IDs, Base record IDs, hashes, and terminal status.

Never change the approved payload after approval. If content must change, rerun review and approval.

## Failure Handling

Use this decision table:

| Failure | Agent action |
| --- | --- |
| Missing env or destination ID | Ask user for the missing value. |
| OpenClaw skill install fails | Report command output and ask whether to install globally, agent-bound, or from a different path. |
| `lark-cli/feishu-cli` unavailable | Ask user to install/configure Feishu CLI. |
| Approval rejected | Use `replan_advisor`; rerun minimal subagents. |
| Archive fails | Do not publish; retry archive or ask user to fix Base permissions/schema. |
| Base read-back fails | Do not publish; retry read-back or ask user to fix Base permissions. |
| Card build fails | Do not publish; inspect Base fields and rebuild. |
| Card publish fails | Retry card publish with the same card hash; do not rewrite Base records. |

## Final Success Criteria

The installation is complete only when:

- `openclaw skills check` passes.
- `scripts/normalize_run_context.py` returns `ok: true`.
- Feishu message dry-run succeeds.
- Feishu Base archive dry-run succeeds.
- Feishu Base read-back dry-run command path succeeds.
- Feishu card build succeeds.
- Feishu card send dry-run succeeds.
- OpenClaw cron job exists or the user explicitly chooses manual-only mode.

Report success to the user with:

```text
ai-news skill 已安装并通过基础验证。
当前模式：<agent/global/local>
目标 OpenClaw agent：<agent id>
定时任务：<cron job id 或 manual-only>
飞书审批人：<FEISHU_NEWS_ADMIN_ID>
目标群：<FEISHU_GROUP_CHAT_ID>
多维表：<FEISHU_BASE_APP_TOKEN>/<FEISHU_BASE_TABLE_ID>
后续运行会使用主 agent + 原子 subagent 协作，并在审批通过后先写入多维表、读回数据、构建飞书卡片，再发群。
```
