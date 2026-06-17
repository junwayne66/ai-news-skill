#!/usr/bin/env bash
# Send deployment / workflow notification via OpenClaw Weixin channel when configured.
set -euo pipefail

STATUS="${1:-}"
if [ "$STATUS" = "--status" ]; then
  STATUS="${2:-success}"
  shift 2 || true
fi
STATUS="${STATUS:-success}"

SUMMARY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --summary) SUMMARY="${2:-}"; shift 2 ;;
    --target) TARGET="${2:-}"; shift 2 ;;
  *) SUMMARY="$1"; shift ;;
  esac
done

TARGET="${WEIXIN_NOTIFY_TARGET:-${TARGET:-}}"
MESSAGE="${SUMMARY:-ai-news workflow notification: ${STATUS}}"

if ! command -v openclaw >/dev/null 2>&1; then
  echo '{"ok": false, "error": "openclaw_not_found"}'
  exit 1
fi

if ! openclaw channels list 2>/dev/null | rg -qi 'weixin.*configured|weixin.*enabled'; then
  if ! openclaw channels list --all 2>/dev/null | rg -qi 'weixin'; then
    echo '{"ok": false, "error": "weixin_channel_not_configured", "skipped": true}'
    exit 0
  fi
fi

if [ -z "$TARGET" ]; then
  TARGET="$(openclaw config get channels.weixin.defaultTarget 2>/dev/null || true)"
fi

if [ -z "$TARGET" ]; then
  echo '{"ok": false, "error": "missing_weixin_target", "hint": "set WEIXIN_NOTIFY_TARGET or channels.weixin.defaultTarget"}'
  exit 0
fi

TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
BODY="[ai-news] ${STATUS}
${MESSAGE}
time: ${TIMESTAMP}"

if openclaw message send --channel weixin --target "$TARGET" --message "$BODY"; then
  echo "{\"ok\": true, \"channel\": \"weixin\", \"target\": \"$TARGET\", \"status\": \"$STATUS\"}"
  exit 0
fi

echo '{"ok": false, "error": "weixin_send_failed"}'
exit 1
