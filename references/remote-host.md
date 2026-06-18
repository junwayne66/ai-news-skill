# Remote Host Environment

Use this reference when deploying, updating, or running end-to-end tests for `ai-news` on the production OpenClaw host.

## SSH Login

Prefer the external host `remote-spark` when deploying from outside the intranet. Use `spark` only when on the same LAN.

| Environment | Command | Auth |
| --- | --- | --- |
| External network (preferred for deploy) | `ssh remote-spark` | passwordless SSH (`~/.ssh/config` on operator Mac) |
| Intranet | `ssh spark` | passwordless SSH |

Operator Mac SSH config path: `/Users/btkj_wayne/.ssh/config`

Cloud Agent environments do not inherit your local `~/.ssh/config`. Provide hostnames via environment variables or create `~/.ssh/config` in the agent VM:

```bash
# Option A: environment variables (no config file)
export SSH_HOST_SPARK="<intranet-ip-or-hostname>"
export SSH_HOST_REMOTE_SPARK="<external-ip-or-hostname>"
./scripts/remote_deploy.sh

# Option B: ~/.ssh/config in the agent VM
cat >> ~/.ssh/config <<'EOF'
Host spark
  HostName <intranet-ip-or-hostname>
  User wayne
  IdentityFile ~/.ssh/id_ed25519

Host remote-spark
  HostName <external-ip-or-hostname>
  User wayne
  IdentityFile ~/.ssh/id_ed25519
EOF
chmod 600 ~/.ssh/config
```

One-command remote deploy (from a machine with SSH access):

```bash
./scripts/remote_deploy.sh
```

This syncs the repo, runs `openclaw update`, reinstalls the skill, executes `scripts/e2e_smoke_test.sh`, and sends a WeChat notification when the Weixin channel is configured.

Quick connectivity check:

```bash
ssh spark 'echo ok && hostname && whoami'
```

If intranet fails, retry:

```bash
ssh remote-spark 'echo ok && hostname && whoami'
```

## Remote Paths

| Purpose | Path |
| --- | --- |
| OpenClaw root | `/home/wayne/.openclaw` |
| Claude Code root | `/home/wayne/.claude` |
| Shared memory | `/home/wayne/.share/memory` |
| Shared skills | `/home/wayne/.share/skills` |

Recommended skill install target on remote host:

```text
/home/wayne/.share/skills/ai-news
```

OpenClaw may also mirror or reference skills under:

```text
/home/wayne/.openclaw/workspace/skills/ai-news
```

Always confirm the active install path with:

```bash
ssh spark 'openclaw skills info ai-news'
```

## Standard Remote Deploy Flow

```bash
# 1) Sync repo to shared skills directory
rsync -av --delete \
  --exclude '.git' \
  ./ \
  spark:/home/wayne/.share/skills/ai-news/

# 2) Install or refresh skill in OpenClaw
ssh spark 'openclaw update && openclaw skills install /home/wayne/.share/skills/ai-news --as ai-news --force && openclaw skills check && openclaw skills info ai-news'
```

If `spark` is unreachable:

```bash
rsync -av --delete --exclude '.git' ./ remote-spark:/home/wayne/.share/skills/ai-news/
ssh remote-spark 'openclaw update && openclaw skills install /home/wayne/.share/skills/ai-news --as ai-news --force && openclaw skills check'
```

## Remote Smoke Test

```bash
ssh spark 'cd /home/wayne/.share/skills/ai-news && ./scripts/e2e_smoke_test.sh'
```

For OpenClaw-level verification:

```bash
ssh spark 'openclaw skills info ai-news && openclaw cron list'
```

## Secrets And Runtime Config

Do not store passwords, tokens, or private keys in this file.

Remote secrets should live in:

- OpenClaw secret manager / runtime env on the remote host
- `lark-cli` auth on the remote host
- files under `/home/wayne/.openclaw` managed by the operator

Typical runtime variables still required on the remote host:

- `FEISHU_NEWS_ADMIN_ID`
- `FEISHU_GROUP_CHAT_ID`
- `FEISHU_BASE_APP_TOKEN`
- `FEISHU_BASE_TABLE_ID`
- `AI_NEWS_CONFIG` (if not using default `data/config.json`)
- `WEIXIN_NOTIFY_TARGET` (optional override for WeChat notify recipient)
- `WEIXIN_NOTIFY_ACCOUNT` (optional override for WeChat account id)

## WeChat Notification (openclaw-weixin)

Proactive WeChat delivery requires a **fresh** `contextToken` tied to an active WeChat session.
Persisted tokens in `*.context-tokens.json` may look present while the upstream API returns `session timeout`.

```bash
# Patch plugin once (also run by remote_deploy / setup_wechat_daily_remote)
./scripts/patch_weixin_outbound.sh

# Verify config
python3 scripts/verify_wechat_notify.py

# Live send (short message)
python3 scripts/verify_wechat_notify.py --live --message "[ai-news] manual verification"

# Send daily report in chunks (recommended for long content)
./scripts/send_wechat_report.sh /path/to/report.md
```

If delivery fails with `session timeout` or `contextToken missing` in `/tmp/openclaw/openclaw-*.log`:
1. Send **any message** to the bot in WeChat (refreshes session token in gateway memory)
2. Retry within a few minutes
3. For daily cron, use `scripts/ai-news-daily-weixin.sh` wrapper (`setup_wechat_daily_remote.sh`) instead of cron `announce` delivery

Chunk size default: `WEIXIN_CHUNK_MAX_CHARS=1500` (only used when report exceeds `WEIXIN_SINGLE_MESSAGE_MAX_CHARS`, default 3800).

**Important:** WeChat proactive push can usually deliver only **one message per fresh session**. Daily reports under 3800 characters are sent as a single bubble. Longer reports are truncated with a note instead of unreliable multi-bubble proactive sends.

1. Try `ssh spark` before `ssh remote-spark`.
2. Treat `/home/wayne/.share/skills` as the canonical shared skill source directory.
3. Treat `/home/wayne/.openclaw` as the OpenClaw runtime root.
4. After deploy, verify with `openclaw skills info ai-news` on the remote host.
5. Do not publish to Feishu groups during dry-run unless the operator explicitly requests a live test.
