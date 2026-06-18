# WeChat (openclaw-weixin) Delivery

## Why session expires

Weixin ilink issues a per-inbound-message `contextToken`. It is meant to be echoed **inside the same conversation turn** when the bot replies to a user message.

| Path | Works on phone? | Notes |
| --- | --- | --- |
| Inbound → agent reply (`process-message` deliver) | Yes | Logs `outbound: text sent OK` |
| Proactive `openclaw message send` / direct `sendmessage` API | Usually **no** | May return `messageId` or API `errcode: -14 session timeout` |
| Disk `*.context-tokens.json` | Unreliable for push | Token is persisted but proactive API still times out |

**Conclusion:** morning cron cannot depend on unsolicited WeChat push with the current ilink bot API.

## Recommended production flow

```text
08:00 cron → ai-news loop → reports/YYYY-MM-DD.md
          → send_wechat_report.sh
              → copy to reports/weixin-pending.md
              → try proactive (best effort)
              → if fail: user replies「发日报」in WeChat
          → agent reads weixin-pending.md and replies verbatim (reliable)
```

### User trigger words

- `发日报`
- `日报`
- `早报`

### Agent rule (main session)

When the user sends one of the trigger words in the WeChat direct session:

1. Read `~/.openclaw/workspace/ai-news/reports/weixin-pending.md` (or latest `reports/YYYY-MM-DD.md`)
2. Reply with the **complete file contents**, unchanged
3. Do not summarize, truncate, or add commentary unless the file is missing

## Alternatives to「user must message first every day」

| Option | Pros | Cons |
| --- | --- | --- |
| **On-demand 发日报** (current) | Reliable, no false success | User sends one keyword after cron |
| **Pending queue on any inbound** | User's normal chat also delivers pending report | Still needs user to open chat |
| **Feishu / email push** | True unsolicited push | Different channel |
| **WeChat subscription / template message** | True push | Requires Tencent product capability outside ilink bot |
| **Enterprise WeChat app message** | Push to corp users | Different integration |

There is no supported workaround that sends ilink bot messages to a silent user every morning without one of the above channels.

## Scripts

```bash
# Stage + try proactive send
./scripts/send_wechat_report.sh reports/2026-06-18.md

# Verify channel / token
python3 scripts/verify_wechat_notify.py
```

Environment:

- `WEIXIN_SINGLE_MESSAGE_MAX_CHARS` (default `3800`)
- `WEIXIN_PENDING_REPORT` (default `~/.openclaw/workspace/ai-news/reports/weixin-pending.md`)

## Logs

```bash
grep -E 'inbound message|text sent OK|session timeout' /tmp/openclaw/openclaw-$(date +%F).log | tail -20
```
