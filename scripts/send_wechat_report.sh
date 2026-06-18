#!/usr/bin/env bash
# Stage and attempt WeChat report delivery; fall back to on-demand reply trigger.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

REPORT_FILE="${1:-}"
if [ -z "$REPORT_FILE" ] || [ ! -f "$REPORT_FILE" ]; then
  echo "usage: $0 <report-file>" >&2
  exit 2
fi

"$PYTHON" - "$ROOT" "$REPORT_FILE" <<'PY'
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "scripts"))
from verify_wechat_notify import (
    resolve_account,
    resolve_context_token,
    resolve_target,
    channel_configured,
    openclaw_bin,
)
from wechat_delivery import recent_inbound_minutes, reply_delivery_hint, stage_pending_report
from wechat_message import load_weixin_account, prepare_outbound_messages, send_messages

report_path = Path(sys.argv[2])
text = report_path.read_text(encoding="utf-8").strip()
if not text:
    print(json.dumps({"ok": False, "error": "empty_report"}, ensure_ascii=False))
    raise SystemExit(2)

staged = stage_pending_report(report_path)
home = Path.home()
openclaw = openclaw_bin()
recent = recent_inbound_minutes() is not None

result: dict = {
    "staged": staged,
    "delivery_mode": "proactive_then_reply_fallback",
    "recent_inbound": recent,
}

if not channel_configured(openclaw):
    result.update({"ok": False, "error": "weixin_channel_not_configured", "hint": reply_delivery_hint(recent_inbound=recent)})
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(2)

account = resolve_account(home)
target = resolve_target(home, account or "")
token = resolve_context_token(home, account or "", target or "") if account and target else None
account_config = load_weixin_account(home, account) if account else {}
if not account or not target:
    result.update({"ok": False, "error": "missing_weixin_target_or_account", "hint": reply_delivery_hint(recent_inbound=recent)})
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(2)

chunks = prepare_outbound_messages(text)
send_result = send_messages(
    openclaw=openclaw,
    account=account,
    target=target,
    messages=chunks,
    context_token=token,
    account_config=account_config,
)
result.update(send_result)
result["report_file"] = str(report_path)
result["report_chars"] = len(text)

if not send_result.get("ok"):
    result["hint"] = reply_delivery_hint(recent_inbound=recent)
    result["trigger_words"] = ["发日报", "日报", "早报"]
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(2)

result["mode"] = "proactive"
print(json.dumps(result, ensure_ascii=False))
PY
