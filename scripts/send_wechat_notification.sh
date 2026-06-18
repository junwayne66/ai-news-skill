#!/usr/bin/env bash
# Send deployment / workflow notification via OpenClaw Weixin channel when configured.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

STATUS="${1:-}"
if [ "$STATUS" = "--status" ]; then
  STATUS="${2:-success}"
  shift 2 || true
fi
STATUS="${STATUS:-success}"

SUMMARY=""
LIVE="${AI_NEWS_WECHAT_LIVE:-0}"
while [ $# -gt 0 ]; do
  case "$1" in
    --summary) SUMMARY="${2:-}"; shift 2 ;;
    --live) LIVE=1; shift ;;
    *) SUMMARY="$1"; shift ;;
  esac
done

MESSAGE="${SUMMARY:-ai-news workflow notification: ${STATUS}}"
export AI_NEWS_WECHAT_LIVE="$LIVE"

if [ "$LIVE" = "1" ]; then
  "$PYTHON" "$ROOT/scripts/verify_wechat_notify.py" --live --message "[ai-news] ${STATUS}
${MESSAGE}"
else
  # Default path: verify config/token, then send live (production deploy notifications).
  "$PYTHON" "$ROOT/scripts/verify_wechat_notify.py" >/tmp/ai-news-weixin-verify.json
  if ! "$PYTHON" - <<'PY'
import json, sys
data = json.load(open('/tmp/ai-news-weixin-verify.json', encoding='utf-8'))
raise SystemExit(0 if data.get('ok') else 1)
PY
  then
    cat /tmp/ai-news-weixin-verify.json
    exit 2
  fi
  "$PYTHON" "$ROOT/scripts/verify_wechat_notify.py" --live --message "[ai-news] ${STATUS}
${MESSAGE}"
fi
