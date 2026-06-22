# OpenClaw Runtime

This skill runs on OpenClaw or Hermes. OpenClaw is the scheduler, agent runtime, secret provider, retry controller, and manual-run interface.

## Runtime Contract

The platform provides environment variables, task payload JSON, or both. `scripts/normalize_run_context.py` converts them into a stable `RunContext`.

```json
{
  "platform": "openclaw",
  "mode": "daily|weekly",
  "report_type": "daily|weekly",
  "requires_approval": false,
  "trigger_type": "scheduled|manual_retry",
  "scheduled_at": "ISO-8601",
  "timezone": "Asia/Shanghai",
  "attempt": 1,
  "trace_id": "openclaw-run-id",
  "max_items": 8,
  "language": "zh-CN",
  "publish_chat_id": "oc_xxx",
  "base_app_token": "xxx",
  "base_table_id": "tbl_xxx"
}
```

Derived fields:

```text
job_id = "ai-news-" + local_date + "-" + timezone_slug          (daily)
job_id = "ai-news-weekly-" + local_date + "-" + timezone_slug   (weekly)
window_end = scheduled_at
window_start = scheduled_at - configured window (24h or 7d)
```

## Cron Schedule

| Cron | Job | Mode | Window |
| --- | --- | --- | --- |
| `0 8 * * 1-5` | Weekday daily news | `daily` | 24h |
| `0 20 * * 0` | Sunday weekly digest | `weekly` | 7d |

Quick setup:

```bash
bash scripts/setup_schedule.sh
```

Manual equivalent:

```bash
openclaw cron create "0 8 * * 1-5" \
  'Use $ai-news to run the daily AI industry news workflow for the previous 24 hours with AI_NEWS_MODE=daily. Cover embodied intelligence, robotics, and world models. After internal review, archive to Base, build card with source links, publish directly to group. No admin approval.' \
  --name "AI News Daily Weekdays" --agent main --session isolated --no-deliver

openclaw cron create "0 20 * * 0" \
  'Use $ai-news to run the weekly AI industry news workflow for the previous 7 days with AI_NEWS_MODE=weekly. Select hottest items. Archive, build weekly card with source links, publish directly to group. No admin approval.' \
  --name "AI News Weekly Sunday" --agent main --session isolated --no-deliver
```

`--session isolated` avoids stale context. `--no-deliver` disables OpenClaw default delivery because this skill sends Feishu cards itself.

## Main Agent Runtime Duties

- Call `scripts/normalize_run_context.py` before collection.
- Stop if required Feishu destination IDs are missing.
- Use `scripts/query_memory.py` before assigning each role.
- After internal quality review, archive → read-back → build card → publish directly.
- Do not wait for administrator approval.

## Retry Policy

- `job_id + payload_hash` is the publish idempotency key.
- `job_id + item_id` is the archive idempotency key.
- If archiving fails, do not publish; retry archive only.
- If card publishing fails after archive success, retry card publish with the same card hash.
