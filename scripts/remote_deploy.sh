#!/usr/bin/env bash
# Remote deploy ai-news-skill to production OpenClaw host (spark / remote-spark).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SSH_HOST="${SSH_HOST:-spark}"
REMOTE_SKILL_DIR="${REMOTE_SKILL_DIR:-/home/wayne/.share/skills/ai-news}"
REMOTE_USER="${REMOTE_USER:-wayne}"
FALLBACK_HOST="${SSH_FALLBACK_HOST:-remote-spark}"

log() { printf '[deploy] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

resolve_ssh_target() {
  local alias="$1"
  if ssh -o BatchMode=yes -o ConnectTimeout=8 -G "$alias" 2>/dev/null | awk '/^hostname /{print $2}' | rg -qv '^'"$alias"'$'; then
    echo "$alias"
    return 0
  fi
  local env_key="SSH_HOST_$(echo "$alias" | tr '[:lower:]-' '[:upper:]_')"
  local host_from_env="${!env_key:-}"
  if [ -n "$host_from_env" ]; then
    echo "${REMOTE_USER}@${host_from_env}"
    return 0
  fi
  return 1
}

pick_host() {
  if resolve_ssh_target "$SSH_HOST" >/dev/null 2>&1 || ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_HOST" 'echo ok' >/dev/null 2>&1; then
    echo "$SSH_HOST"
    return 0
  fi
  log "primary host '$SSH_HOST' unreachable, trying fallback '$FALLBACK_HOST'"
  if resolve_ssh_target "$FALLBACK_HOST" >/dev/null 2>&1 || ssh -o BatchMode=yes -o ConnectTimeout=8 "$FALLBACK_HOST" 'echo ok' >/dev/null 2>&1; then
    echo "$FALLBACK_HOST"
    return 0
  fi
  die "cannot reach '$SSH_HOST' or '$FALLBACK_HOST'. Configure ~/.ssh/config or set SSH_HOST_SPARK / SSH_HOST_REMOTE_SPARK."
}

HOST="$(pick_host)"
TARGET="${HOST}:${REMOTE_SKILL_DIR}"
log "using host: $HOST"

log "syncing repo to $TARGET"
rsync -av --delete \
  --exclude '.git' \
  --exclude 'data/runs' \
  --exclude '__pycache__' \
  ./ \
  "$TARGET/"

REMOTE_CMD=$(cat <<'EOS'
set -euo pipefail
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:/usr/local/bin:$PATH"
openclaw update
openclaw skills install REMOTE_SKILL_DIR_PLACEHOLDER --as ai-news --force
openclaw skills check
openclaw skills info ai-news
cd REMOTE_SKILL_DIR_PLACEHOLDER
chmod +x scripts/*.py scripts/*.sh 2>/dev/null || true
./scripts/e2e_smoke_test.sh
EOS
)
REMOTE_CMD="${REMOTE_CMD//REMOTE_SKILL_DIR_PLACEHOLDER/$REMOTE_SKILL_DIR}"

log "updating OpenClaw and reinstalling ai-news skill"
ssh -o BatchMode=yes "$HOST" "$REMOTE_CMD"

log "sending WeChat deployment notification (if configured)"
ssh -o BatchMode=yes "$HOST" "cd '$REMOTE_SKILL_DIR' && ./scripts/send_wechat_notification.sh --status success --summary 'ai-news-skill deployed and e2e passed on $(hostname)'" \
  || log "WeChat notification skipped or failed (channel may be unconfigured)"

log "remote deploy complete"
