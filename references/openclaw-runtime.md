# OpenClaw Runtime

This skill is OpenClaw-only. Treat OpenClaw as the scheduler, agent runtime, secret provider, retry controller, and manual-run interface.

## Runtime Contract

OpenClaw should provide either environment variables, task payload JSON, or both. `scripts/normalize_run_context.py` converts them into a stable `RunContext`.

```json
{
  "platform": "openclaw",
  "trigger_type": "scheduled|manual_retry|approval_resume",
  "scheduled_at": "ISO-8601",
  "timezone": "Asia/Shanghai",
  "attempt": 1,
  "trace_id": "openclaw-run-id",
  "config": {
    "news_window": "24h",
    "max_items": 8,
    "language": "zh-CN"
  },
  "destinations": {
    "approval_user_id": "ou_xxx",
    "publish_chat_id": "oc_xxx",
    "base_app_token": "base_xxx",
    "base_table_id": "tbl_xxx"
  }
}
```

Derived fields:

```text
job_id = "ai-news-" + local_date + "-" + timezone_slug
window_end = scheduled_at
window_start = scheduled_at - configured window
```

## Cron Shape

Use OpenClaw cron for the daily trigger:

```bash
openclaw cron create "0 9 * * *" \
  'Use $ai-news to run the daily AI industry news workflow for the previous 24 hours. Use deterministic scripts for OpenClaw context normalization, Feishu approval notification, Base archive, Base read-back, Feishu card building, and group publishing. Use atomic subagents for uncertain news collection, verification, ranking, editing, and review. Do not publish before approval and Base archive success.' \
  --name "AI News Daily" \
  --agent ops \
  --session isolated \
  --no-deliver
```

`--session isolated` keeps daily runs from inheriting stale conversation context. `--no-deliver` keeps OpenClaw's default delivery quiet because this skill sends approved Feishu messages itself.

## Main Agent Runtime Duties

The main task agent must:

- Call `scripts/normalize_run_context.py` before any collection.
- Stop if required Feishu destination IDs or secrets are missing.
- Use `scripts/query_memory.py` before assigning each role.
- Maintain the task board and route subagent messages.
- Advance state only after deterministic scripts or subagents return structured status.
- Persist important run artifacts in OpenClaw run output, Feishu Base, or the configured state store.

## Retry Policy

OpenClaw may retry a failed cron run. The main agent must make publish and archive idempotent:

- `job_id + approved_payload_hash` is the publish idempotency key.
- `job_id + item_id` is the archive idempotency key.
- If archiving fails, do not publish; retry archive only.
- If card publishing fails after archive success, retry card publish only with the same card hash.
- If approval is rejected, do not rely on platform retry. Replan explicitly from the administrator feedback.

## Approval Resume

Fast MVP uses manual approval:

```text
管理员回复: 同意发布 <payload_hash>
管理员回复: 驳回 <feedback>
```

The main agent resumes through a manual OpenClaw run or follow-up task, validates the hash, and either publishes or replans.

Full automation can add Feishu interactive cards and callback validation, but callback verification must remain deterministic code.
