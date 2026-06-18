#!/usr/bin/env bash
# Send a daily AI news report to WeChat in multiple chunks when needed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

REPORT_FILE="${1:-}"
if [ -z "$REPORT_FILE" ] || [ ! -f "$REPORT_FILE" ]; then
  echo "usage: $0 <report-file>" >&2
  exit 2
fi

"$ROOT/scripts/patch_weixin_outbound.sh" || true

"$PYTHON" - "$ROOT" "$REPORT_FILE" <<'PY'
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "scripts"))
from verify_wechat_notify import resolve_account, resolve_context_token, resolve_target, channel_configured, openclaw_bin
from wechat_message import split_message, send_messages

report_path = Path(sys.argv[2])
text = report_path.read_text(encoding="utf-8").strip()
if not text:
    print(json.dumps({"ok": False, "error": "empty_report"}, ensure_ascii=False))
    raise SystemExit(2)

home = Path.home()
openclaw = openclaw_bin()
if not channel_configured(openclaw):
    print(json.dumps({"ok": False, "error": "weixin_channel_not_configured"}, ensure_ascii=False))
    raise SystemExit(2)

account = resolve_account(home)
target = resolve_target(home, account or "")
token = resolve_context_token(home, account or "", target or "") if account and target else None
if not account or not target:
    print(json.dumps({"ok": False, "error": "missing_weixin_target_or_account"}, ensure_ascii=False))
    raise SystemExit(2)

chunks = split_message(text)
result = send_messages(
    openclaw=openclaw,
    account=account,
    target=target,
    messages=chunks,
    context_token=token,
)
result["mode"] = "report-chunks"
result["report_file"] = str(report_path)
result["report_chars"] = len(text)
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(0 if result.get("ok") else 2)
PY
