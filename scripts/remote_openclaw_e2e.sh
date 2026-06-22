#!/usr/bin/env bash
# Run on the OpenClaw host (btkj-agent) after cloning/syncing ai-news skill.
set -euo pipefail

AI_NEWS_DIR="${AI_NEWS_DIR:-$HOME/ai-news-skill}"
AI_NEWS_AGENT_ID="${AI_NEWS_AGENT_ID:-ops}"
FEISHU_GROUP_CHAT_ID="${FEISHU_GROUP_CHAT_ID:-oc_9aa22f921c03f6ea5db59808deb08691}"
OPENCLAW_MODEL_DEFAULT="${OPENCLAW_MODEL_DEFAULT:-botinkit/smart-router}"
OPENCLAW_MODEL_COMPLEX="${OPENCLAW_MODEL_COMPLEX:-botinkit/deepseek-v4-pro}"
LARK_CLI_BIN="${LARK_CLI_BIN:-lark-cli}"
LARK_CLI_AS="${LARK_CLI_AS:-bot}"

log() { printf '[remote-e2e] %s\n' "$*"; }
fail() { printf '[remote-e2e] ERROR: %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

log "Phase 0: prerequisites"
require_cmd openclaw
require_cmd python3
require_cmd "$LARK_CLI_BIN"

openclaw --help >/dev/null
openclaw config set tools.profile "coding" || true

log "Phase 1: install Agent Reach (internet capability layer)"
if ! command -v agent-reach >/dev/null 2>&1; then
  if command -v pipx >/dev/null 2>&1; then
    pipx install https://github.com/Panniantong/agent-reach/archive/main.zip || true
  else
    python3 -m pip install --user https://github.com/Panniantong/agent-reach/archive/main.zip || true
  fi
fi
if command -v agent-reach >/dev/null 2>&1; then
  agent-reach install --env=auto || true
  agent-reach doctor --json | head -c 4000 || true
else
  log "Agent Reach not installed; ai-news will run in rss_only mode"
fi

log "Phase 2: install ai-news skill"
test -f "$AI_NEWS_DIR/SKILL.md" || fail "SKILL.md not found at $AI_NEWS_DIR"
chmod +x "$AI_NEWS_DIR"/scripts/*.py
openclaw skills install "$AI_NEWS_DIR" --as ai-news --agent "$AI_NEWS_AGENT_ID" --force
openclaw skills check --agent "$AI_NEWS_AGENT_ID"
openclaw skills info ai-news --agent "$AI_NEWS_AGENT_ID"

log "Phase 3: configure models"
# Adjust keys if your OpenClaw version uses a different config schema.
openclaw config set agents."$AI_NEWS_AGENT_ID".model "$OPENCLAW_MODEL_DEFAULT" 2>/dev/null \
  || openclaw config set agent."$AI_NEWS_AGENT_ID".model "$OPENCLAW_MODEL_DEFAULT" 2>/dev/null \
  || log "Could not set default model automatically; set $OPENCLAW_MODEL_DEFAULT manually"
log "Default model target: $OPENCLAW_MODEL_DEFAULT"
log "Complex model target: $OPENCLAW_MODEL_COMPLEX"

log "Phase 4: deterministic script smoke tests"
export AI_NEWS_PLATFORM=openclaw
export AI_NEWS_TIMEZONE=Asia/Shanghai
export FEISHU_GROUP_CHAT_ID
export LARK_CLI_BIN LARK_CLI_AS

cd "$AI_NEWS_DIR"
scripts/sync_agent_reach_health.py || true
scripts/check_news_sources.py --refresh-reach || true
scripts/query_memory.py --query "agent reach integration channel policy" --top-k 2

if [[ -n "${FEISHU_NEWS_ADMIN_ID:-}" && -n "${FEISHU_BASE_APP_TOKEN:-}" && -n "${FEISHU_BASE_TABLE_ID:-}" ]]; then
  scripts/normalize_run_context.py
else
  log "Skipping normalize_run_context (set FEISHU_NEWS_ADMIN_ID, FEISHU_BASE_APP_TOKEN, FEISHU_BASE_TABLE_ID for full workflow)"
fi

log "Phase 5: Feishu connectivity"
"$LARK_CLI_BIN" auth status

log "Phase 5a: dry-run text message"
scripts/send_feishu_message.py \
  --receive-id "$FEISHU_GROUP_CHAT_ID" \
  --receive-id-type chat_id \
  --text "AI News E2E dry-run connectivity test" \
  --dry-run

log "Phase 5b: live text message to group"
scripts/send_feishu_message.py \
  --receive-id "$FEISHU_GROUP_CHAT_ID" \
  --receive-id-type chat_id \
  --text "AI News E2E 连通性测试 $(date -Iseconds)"

log "Phase 6: optional full ai-news dry-run via OpenClaw agent"
openclaw agent --agent "$AI_NEWS_AGENT_ID" --message \
  "Use \$ai-news to run a source-check dry-run only. Sync Agent Reach health, build routing, collect up to 3 candidates, prepare approval draft if possible, but do not publish to the group unless explicitly approved."

log "Done. Review OpenClaw output above for agent workflow results."
