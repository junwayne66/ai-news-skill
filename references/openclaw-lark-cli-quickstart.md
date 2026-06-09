# OpenClaw + lark-cli Quickstart

This guide gets the AI News skill running on OpenClaw with Feishu capabilities through the official `lark-cli`.

## Assumptions

- `lark-cli` is already installed and configured on the OpenClaw host.
- `lark-cli auth status` succeeds for the identity that will send messages.
- The Feishu app or user has permissions for Messenger and Base operations.
- You know these IDs:
  - Feishu news administrator receive ID, such as `open_id` or `user_id`.
  - Target Feishu group chat ID, usually `oc_xxx`.
  - Feishu Base `app_token`.
  - Feishu Base `table_id`.

## Install the Skill

From the OpenClaw host, install this skill directory. The source root must contain `SKILL.md`.

```bash
openclaw skills install /path/to/ai-news --as ai-news --force
openclaw skills check
openclaw skills info ai-news
```

If the skill should be visible to every workspace, use:

```bash
openclaw skills install /path/to/ai-news --as ai-news --global --force
```

If it should be pinned to one agent:

```bash
openclaw skills install /path/to/ai-news --as ai-news --agent ops --force
openclaw skills check --agent ops
```

## Verify lark-cli Access

```bash
lark-cli auth status
lark-cli im +messages-send --as bot --chat-id "oc_xxx" --text "AI News skill connectivity test" --dry-run
```

For raw API verification:

```bash
lark-cli api POST /open-apis/im/v1/messages \
  --params '{"receive_id_type":"chat_id"}' \
  --data '{"receive_id":"oc_xxx","msg_type":"text","content":"{\"text\":\"AI News raw API dry run\"}"}' \
  --dry-run
```

## Configure Environment

Put these in the OpenClaw agent runtime environment, secret manager, or cron wrapper:

```bash
export AI_NEWS_PLATFORM=openclaw
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
```

`FEISHU_NEWS_ADMIN_ID_TYPE` should match the admin ID type. Use `open_id` when possible. For group publishing use `chat_id`.

## Smoke Test Deterministic Scripts

```bash
scripts/normalize_run_context.py

printf '%s\n' '{"receive_id_type":"chat_id","receive_id":"oc_xxx","text":"AI News test","dry_run":true}' \
  | scripts/send_feishu_message.py

printf '%s\n' '{"records":[{"fields":{"标题":"AI News test","摘要":"dry run"}}]}' \
  | scripts/archive_feishu_base.py --dry-run
```

## Create a Daily OpenClaw Cron Job

Recommended prompt:

```text
Use $ai-news to run the daily AI industry news workflow for the previous 24 hours.
Use scripts for deterministic steps and atomic subagents for collection, verification, ranking, editing, and review.
Send the frozen draft to FEISHU_NEWS_ADMIN_ID for approval first.
Only after approval, archive final records to Feishu Base, fetch the archived records, build a Feishu card from fetched fields, and publish that card to FEISHU_GROUP_CHAT_ID.
If approval is rejected, use the feedback to rerun the smallest necessary subagent steps and request approval again.
```

Create the scheduled job:

```bash
openclaw cron create "0 9 * * *" \
  'Use $ai-news to run the daily AI industry news workflow for the previous 24 hours. Use lark-cli scripts for Feishu approval, Base archive, Base read-back, Feishu card building, and group publishing. Do not publish before approval and Base archive success.' \
  --name "AI News Daily" \
  --agent ops \
  --session isolated \
  --no-deliver
```

Manually test:

```bash
openclaw cron list --agent ops
openclaw cron run <job-id> --wait --wait-timeout 30m
openclaw cron runs --id <job-id> --limit 10
```

## Fast Approval MVP

For the fastest first version, use Feishu direct messages for approval:

1. Main agent drafts the report and computes `payload_hash`.
2. `scripts/send_feishu_message.py` sends the draft to the administrator.
3. Administrator replies with `同意发布 <payload_hash>` or `驳回 <feedback>`.
4. A manual or event-triggered OpenClaw run resumes the job using that decision.
5. Records are written with `scripts/archive_feishu_base.py`.
6. The archived records are fetched with `scripts/fetch_feishu_base_records.py`.
7. The group card is built from fetched fields with `scripts/build_feishu_card.py`.
8. The card is sent to the group with `scripts/send_feishu_card.py`.

For full automation, add `send_feishu_approval.py` and `validate_feishu_callback.py` to use Feishu interactive cards and callback validation.

## Operational Notes

- Always run `--dry-run` first for new Feishu destinations.
- Keep Feishu credentials in `lark-cli` config or OpenClaw secrets, not inside prompts.
- Do not grant Base write permissions broader than the target app/table needs.
- Keep cron output internal with `--no-deliver`; the skill itself sends approved Feishu messages.
- Use isolated cron sessions so daily runs do not inherit stale conversation context.
