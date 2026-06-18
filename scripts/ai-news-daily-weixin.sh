#!/usr/bin/env bash
# Cron wrapper: run ai-news loop, then deliver report to WeChat in chunks.
set -euo pipefail

SKILL_ROOT="${AI_NEWS_SKILL_ROOT:-/home/wayne/.share/skills/ai-news}"
LOOP_BIN="${AI_NEWS_LOOP_BIN:-/home/wayne/.openclaw/bin/ai-news-daily}"
REPORT_FILE="${AI_NEWS_DAILY_REPORT_FILE:-/tmp/ai-news-daily-$(date +%F).txt}"

export PATH="${HOME}/.openclaw/bin:${HOME}/.openclaw/tools/node-v22.22.0/bin:${PATH}"

set +e
"$LOOP_BIN" "$@" | tee "$REPORT_FILE"
loop_rc=${PIPESTATUS[0]}
set -e

if [ ! -s "$REPORT_FILE" ]; then
  echo "[ai-news-daily-weixin] empty report, skip wechat delivery" >&2
  exit "$loop_rc"
fi

if ! "$SKILL_ROOT/scripts/send_wechat_report.sh" "$REPORT_FILE"; then
  echo "[ai-news-daily-weixin] wechat delivery failed (loop rc=$loop_rc)" >&2
  exit 2
fi

exit "$loop_rc"
