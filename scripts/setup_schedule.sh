#!/usr/bin/env bash
# Create weekday daily and Sunday weekly cron jobs for ai-news.
set -euo pipefail

AI_NEWS_AGENT_ID="${AI_NEWS_AGENT_ID:-main}"
PLATFORM="${AI_NEWS_PLATFORM:-openclaw}"

log() { printf '[setup-schedule] %s\n' "$*"; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { log "missing command: $1"; exit 1; }
}

require_cmd openclaw

DAILY_PROMPT='Use $ai-news to run the daily AI industry news workflow for the previous 24 hours with AI_NEWS_MODE=daily. Cover model releases, funding, policy, research, infra, community signals, embodied intelligence, robotics, and world models. After internal quality review, archive to Feishu Base, build card with clickable source links per item, and publish directly to FEISHU_GROUP_CHAT_ID. Do not wait for administrator approval.'

WEEKLY_PROMPT='Use $ai-news to run the weekly AI industry news workflow for the previous 7 days with AI_NEWS_MODE=weekly. Select the hottest high-signal items across the week. Cover model releases, funding, policy, research, infra, community signals, embodied intelligence, robotics, and world models. After internal quality review, archive to Feishu Base, build weekly card with clickable source links per item, and publish directly to FEISHU_GROUP_CHAT_ID. Do not wait for administrator approval.'

create_job() {
  local name="$1"
  local cron="$2"
  local prompt="$3"
  if openclaw cron create "$cron" "$prompt" \
    --name "$name" \
    --agent "$AI_NEWS_AGENT_ID" \
    --session isolated \
    --no-deliver 2>/dev/null; then
    log "created: $name"
    return 0
  fi
  log "cron create failed for $name; try adapting to your OpenClaw version"
  openclaw cron --help | head -20
  return 1
}

log "Platform: $PLATFORM, agent: $AI_NEWS_AGENT_ID"
create_job "AI News Daily Weekdays" "0 8 * * 1-5" "$DAILY_PROMPT"
create_job "AI News Weekly Sunday" "0 20 * * 0" "$WEEKLY_PROMPT"
openclaw cron list --agent "$AI_NEWS_AGENT_ID" || openclaw cron list
