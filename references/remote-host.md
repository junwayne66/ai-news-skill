# Remote Host Environment

Use this reference when deploying, updating, or running end-to-end tests for `ai-news` on the production OpenClaw host.

## SSH Login

Prefer the intranet host first. Use the external alias only when intranet is unreachable.

| Environment | Command | Auth |
| --- | --- | --- |
| Intranet (preferred) | `ssh spark` | passwordless SSH |
| External network | `ssh remote-spark` | passwordless SSH |

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

## Agent Rules

1. Try `ssh spark` before `ssh remote-spark`.
2. Treat `/home/wayne/.share/skills` as the canonical shared skill source directory.
3. Treat `/home/wayne/.openclaw` as the OpenClaw runtime root.
4. After deploy, verify with `openclaw skills info ai-news` on the remote host.
5. Do not publish to Feishu groups during dry-run unless the operator explicitly requests a live test.
