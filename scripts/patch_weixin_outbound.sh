#!/usr/bin/env bash
# Patch openclaw-weixin plugin for reliable proactive WeChat delivery.
set -euo pipefail

HOME_DIR="${HOME:-/home/wayne}"
PLUGIN_ROOT="${WEIXIN_PLUGIN_ROOT:-$HOME_DIR/.openclaw/npm/projects/tencent-weixin-openclaw-weixin-7783ac86ba}"
CHANNEL_JS="$PLUGIN_ROOT/node_modules/@tencent-weixin/openclaw-weixin/dist/src/channel.js"
INBOUND_JS="$PLUGIN_ROOT/node_modules/@tencent-weixin/openclaw-weixin/dist/src/messaging/inbound.js"

if [ ! -f "$CHANNEL_JS" ]; then
  echo "[patch-weixin] channel.js not found at $CHANNEL_JS" >&2
  exit 0
fi

PATCHED=0

patch_channel_outbound() {
  if grep -q 'const deliveryToken = ctx.delivery?.contextToken ?? ctx.payload?.delivery?.contextToken' "$CHANNEL_JS"; then
    echo "[patch-weixin] channel sendText already patched: $CHANNEL_JS"
  else
    python3 - "$CHANNEL_JS" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old_send_text = """        sendText: async (ctx) => {
            const accountId = ctx.accountId || resolveOutboundAccountId(ctx.cfg, ctx.to);
            const result = await sendWeixinOutbound({
                cfg: ctx.cfg,
                to: ctx.to,
                text: ctx.text,
                accountId,
                contextToken: getContextToken(accountId, ctx.to),
            });"""
new_send_text = """        sendText: async (ctx) => {
            const accountId = ctx.accountId || resolveOutboundAccountId(ctx.cfg, ctx.to);
            const deliveryToken = ctx.delivery?.contextToken ?? ctx.payload?.delivery?.contextToken;
            const result = await sendWeixinOutbound({
                cfg: ctx.cfg,
                to: ctx.to,
                text: ctx.text,
                accountId,
                contextToken: deliveryToken ?? getContextToken(accountId, ctx.to),
            });"""
if old_send_text not in text:
    raise SystemExit(f"sendText patch marker not found in {path}")
path.write_text(text.replace(old_send_text, new_send_text, 1), encoding="utf-8")
print(f"[patch-weixin] patched channel sendText: {path}")
PY
    PATCHED=1
  fi

  if grep -q 'const contextToken = params.contextToken ?? getContextToken' "$CHANNEL_JS"; then
    echo "[patch-weixin] sendWeixinOutbound already patched: $CHANNEL_JS"
    return 0
  fi

  python3 - "$CHANNEL_JS" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old_outbound = """    if (!params.contextToken) {
        aLog.warn(`sendWeixinOutbound: contextToken missing for to=${params.to}, sending without context`);
    }
    const f = new StreamingMarkdownFilter();"""
new_outbound = """    const contextToken = params.contextToken ?? getContextToken(account.accountId, params.to);
    if (!contextToken) {
        aLog.warn(`sendWeixinOutbound: contextToken missing for to=${params.to}, sending without context`);
    }
    const f = new StreamingMarkdownFilter();"""
if old_outbound not in text:
    raise SystemExit(f"sendWeixinOutbound patch marker not found in {path}")
text = text.replace(old_outbound, new_outbound, 1)
text = text.replace(
    "contextToken: params.contextToken,",
    "contextToken: contextToken,",
    1,
)
path.write_text(text, encoding="utf-8")
print(f"[patch-weixin] patched sendWeixinOutbound: {path}")
PY
  PATCHED=1
}

patch_inbound_disk_fallback() {
  if [ ! -f "$INBOUND_JS" ]; then
    echo "[patch-weixin] inbound.js not found, skip disk fallback" >&2
    return 0
  fi
  if grep -q 'getContextToken: disk fallback' "$INBOUND_JS"; then
    echo "[patch-weixin] inbound disk fallback already patched: $INBOUND_JS"
    return 0
  fi

  python3 - "$INBOUND_JS" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = """export function getContextToken(accountId, userId) {
    const k = contextTokenKey(accountId, userId);
    const val = contextTokenStore.get(k);
    logger.debug(`getContextToken: key=${k} found=${val !== undefined} storeSize=${contextTokenStore.size}`);
    return val;
}"""
new = """export function getContextToken(accountId, userId) {
    const k = contextTokenKey(accountId, userId);
    let val = contextTokenStore.get(k);
    if (val === undefined) {
        try {
            const filePath = resolveContextTokenFilePath(accountId);
            if (fs.existsSync(filePath)) {
                const tokens = JSON.parse(fs.readFileSync(filePath, "utf-8"));
                const disk = tokens[userId];
                if (typeof disk === "string" && disk) {
                    contextTokenStore.set(k, disk);
                    val = disk;
                    logger.debug(`getContextToken: disk fallback loaded key=${k}`);
                }
            }
        }
        catch (err) {
            logger.warn(`getContextToken: disk fallback failed account=${accountId}: ${String(err)}`);
        }
    }
    logger.debug(`getContextToken: key=${k} found=${val !== undefined} storeSize=${contextTokenStore.size}`);
    return val;
}"""
if old not in text:
    raise SystemExit(f"getContextToken patch marker not found in {path}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print(f"[patch-weixin] patched inbound disk fallback: {path}")
PY
  PATCHED=1
}

patch_channel_outbound
patch_inbound_disk_fallback

if [ "$PATCHED" -eq 1 ] && command -v openclaw >/dev/null 2>&1; then
  openclaw gateway restart >/dev/null 2>&1 || systemctl --user restart openclaw-gateway.service >/dev/null 2>&1 || true
  echo "[patch-weixin] gateway restarted to load plugin patches"
fi
