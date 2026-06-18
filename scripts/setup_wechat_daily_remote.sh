#!/usr/bin/env bash
# Configure remote host for chunked WeChat daily delivery (disable cron announce).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CRON_ID="${AI_NEWS_WEIXIN_CRON_ID:-c46bb882-4c80-4778-bc9f-1ded4c594fde}"
WRAPPER="${AI_NEWS_DAILY_WRAPPER:-/home/wayne/.openclaw/bin/ai-news-daily-weixin}"

log() { printf '[setup-wechat-daily] %s\n' "$*"; }

chmod +x "$ROOT/scripts/patch_weixin_outbound.sh" \
  "$ROOT/scripts/send_wechat_report.sh" \
  "$ROOT/scripts/ai-news-daily-weixin.sh"

"$ROOT/scripts/patch_weixin_outbound.sh"

cat >"$WRAPPER" <<EOF
#!/usr/bin/env bash
exec "$ROOT/scripts/ai-news-daily-weixin.sh" "\$@"
EOF
chmod +x "$WRAPPER"
log "installed wrapper: $WRAPPER"

if command -v openclaw >/dev/null 2>&1; then
  openclaw cron edit "$CRON_ID" \
    --command "$WRAPPER" \
    --no-deliver \
    --account 7b495fdd64ab-im-bot \
    --to "o9cq808eJohUVnzrwq0WPd_g5fEY@im.wechat" || log "cron edit failed (manual update may be required)"
  log "cron updated: command=$WRAPPER delivery=script"
else
  log "openclaw not in PATH; skip cron edit"
fi

log "done"
