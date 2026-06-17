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
TARGET=""
ACCOUNT="${WEIXIN_NOTIFY_ACCOUNT:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --summary) SUMMARY="${2:-}"; shift 2 ;;
    --target) TARGET="${2:-}"; shift 2 ;;
    --account) ACCOUNT="${2:-}"; shift 2 ;;
    *) SUMMARY="$1"; shift ;;
  esac
done

TARGET="${WEIXIN_NOTIFY_TARGET:-$TARGET}"
MESSAGE="${SUMMARY:-ai-news workflow notification: ${STATUS}}"

if ! command -v openclaw >/dev/null 2>&1; then
  echo '{"ok": false, "error": "openclaw_not_found"}'
  exit 1
fi

if ! openclaw channels list 2>/dev/null | grep -Eiq 'openclaw-weixin.*(configured|enabled)|weixin.*(configured|enabled)'; then
  echo '{"ok": false, "error": "weixin_channel_not_configured", "skipped": true}'
  exit 0
fi

if [ -z "$ACCOUNT" ]; then
  ACCOUNT="$(python3 - <<'PY' 2>/dev/null || true
import json
from pathlib import Path
p = Path.home() / ".openclaw/agents/main/sessions/sessions.json"
if p.exists():
    data = json.loads(p.read_text(encoding="utf-8"))
    for value in data.values():
        origin = value.get("origin") or {}
        if origin.get("provider") == "openclaw-weixin" and origin.get("accountId"):
            print(origin["accountId"])
            raise SystemExit
PY
)"
fi
if [ -z "$ACCOUNT" ]; then
  ACCOUNT="$(openclaw channels list 2>/dev/null | awk '/openclaw-weixin/ && !/default:/ {print $2; exit}')"
fi

if [ -z "$TARGET" ]; then
  TARGET="$(python3 - <<'PY' 2>/dev/null || true
import json
from pathlib import Path
p = Path.home() / ".openclaw/agents/main/sessions/sessions.json"
if not p.exists():
    raise SystemExit
data = json.loads(p.read_text(encoding="utf-8"))
for key, value in data.items():
    if "openclaw-weixin" not in key:
        continue
    route = value.get("route") or {}
    target = (route.get("target") or {}).get("to") or value.get("lastTo")
    if target and value.get("chatType", "direct") == "direct":
        print(target)
        raise SystemExit
PY
)"
fi

if [ -z "$TARGET" ]; then
  echo '{"ok": false, "error": "missing_weixin_target", "hint": "set WEIXIN_NOTIFY_TARGET"}'
  exit 0
fi

TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
BODY="[ai-news] ${STATUS}
${MESSAGE}
time: ${TIMESTAMP}"

SEND_ARGS=(message send --channel openclaw-weixin -t "$TARGET" -m "$BODY")
if [ -n "$ACCOUNT" ]; then
  SEND_ARGS+=(--account "$ACCOUNT")
fi

if openclaw "${SEND_ARGS[@]}"; then
  echo "{\"ok\": true, \"channel\": \"openclaw-weixin\", \"account\": \"$ACCOUNT\", \"target\": \"$TARGET\", \"status\": \"$STATUS\"}"
  exit 0
fi

echo '{"ok": false, "error": "weixin_send_failed"}'
exit 1
