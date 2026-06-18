#!/usr/bin/env bash
# Patch openclaw-weixin plugin so proactive sends fall back to in-memory contextToken.
set -euo pipefail

HOME_DIR="${HOME:-/home/wayne}"
PLUGIN_ROOT="${WEIXIN_PLUGIN_ROOT:-$HOME_DIR/.openclaw/npm/projects/tencent-weixin-openclaw-weixin-7783ac86ba}"
CHANNEL_JS="$PLUGIN_ROOT/node_modules/@tencent-weixin/openclaw-weixin/dist/src/channel.js"

if [ ! -f "$CHANNEL_JS" ]; then
  echo "[patch-weixin] channel.js not found at $CHANNEL_JS" >&2
  exit 0
fi

if grep -q 'const contextToken = params.contextToken ?? getContextToken' "$CHANNEL_JS"; then
  echo "[patch-weixin] already patched: $CHANNEL_JS"
  exit 0
fi

python3 - "$CHANNEL_JS" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = """    if (!params.contextToken) {
        aLog.warn(`sendWeixinOutbound: contextToken missing for to=${params.to}, sending without context`);
    }
    const f = new StreamingMarkdownFilter();"""
new = """    const contextToken = params.contextToken ?? getContextToken(account.accountId, params.to);
    if (!contextToken) {
        aLog.warn(`sendWeixinOutbound: contextToken missing for to=${params.to}, sending without context`);
    }
    const f = new StreamingMarkdownFilter();"""
if old not in text:
    raise SystemExit(f"patch marker not found in {path}")
text = text.replace(old, new, 1)
text = text.replace(
    "contextToken: params.contextToken,",
    "contextToken: contextToken,",
    1,
)
path.write_text(text, encoding="utf-8")
print(f"[patch-weixin] patched {path}")
PY
