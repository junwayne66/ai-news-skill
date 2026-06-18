#!/usr/bin/env bash
# End-to-end deterministic smoke test for ai-news skill scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
PASS=0
FAIL=0
SKIP=0

log() { printf '[e2e] %s\n' "$*"; }
pass() { PASS=$((PASS + 1)); log "PASS: $*"; }
fail() { FAIL=$((FAIL + 1)); log "FAIL: $*"; }
skip() { SKIP=$((SKIP + 1)); log "SKIP: $*"; }

assert_json_ok() {
  local label="$1"
  local file="$2"
  if "$PYTHON" - <<'PY' "$file" "$label"; then
import json, sys
path, label = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding='utf-8'))
ok = data.get('ok')
if ok is False:
    raise SystemExit(f"{label}: ok=false -> {data}")
print(f"{label}: ok")
PY
    pass "$label"
  else
    fail "$label"
  fi
}

log "starting ai-news e2e smoke test in $ROOT"

export FEISHU_NEWS_ADMIN_ID="${FEISHU_NEWS_ADMIN_ID:-ou_test}"
export FEISHU_GROUP_CHAT_ID="${FEISHU_GROUP_CHAT_ID:-oc_test}"
export FEISHU_BASE_APP_TOKEN="${FEISHU_BASE_APP_TOKEN:-base_test}"
export FEISHU_BASE_TABLE_ID="${FEISHU_BASE_TABLE_ID:-tbl_test}"
export AI_NEWS_PLATFORM="${AI_NEWS_PLATFORM:-openclaw}"

"$PYTHON" scripts/normalize_run_context.py < /dev/null > /tmp/e2e-run-context.json
assert_json_ok "normalize_run_context" /tmp/e2e-run-context.json

JOB_ID="$("$PYTHON" - <<'PY'
import json
print(json.load(open('/tmp/e2e-run-context.json'))['run_context']['job_id'])
PY
)"

"$PYTHON" scripts/loop_state.py init --job-id "$JOB_ID-e2e" --platform "$AI_NEWS_PLATFORM" --force > /tmp/e2e-loop-init.json
assert_json_ok "loop_state init" /tmp/e2e-loop-init.json

printf '%s\n' '{"stage":"fetching","candidate_count":0}' | "$PYTHON" scripts/loop_state.py write --job-id "$JOB_ID-e2e" > /tmp/e2e-loop-write.json
assert_json_ok "loop_state write" /tmp/e2e-loop-write.json

"$PYTHON" scripts/query_memory.py --query "fetch_sources url_dedupe" --top-k 2 > /tmp/e2e-memory.json
assert_json_ok "query_memory" /tmp/e2e-memory.json

cat > /tmp/e2e-run-context-input.json <<JSON
{"run_context": $(python3 -c 'import json;print(json.dumps(json.load(open("/tmp/e2e-run-context.json"))["run_context"]))')}
JSON

if "$PYTHON" scripts/fetch_sources.py --config data/config.example.json --input /tmp/e2e-run-context-input.json --include-collector-candidates --timeout-sec 10 > /tmp/e2e-prefetched.json; then
  assert_json_ok "fetch_sources" /tmp/e2e-prefetched.json
else
  fail "fetch_sources"
fi

"$PYTHON" scripts/url_dedupe.py --input /tmp/e2e-prefetched.json > /tmp/e2e-deduped.json
assert_json_ok "url_dedupe" /tmp/e2e-deduped.json

cat > /tmp/e2e-draft.json <<'JSON'
{
  "report_date": "2026-06-17",
  "timezone": "Asia/Shanghai",
  "window_start": "2026-06-16T09:00:00+08:00",
  "window_end": "2026-06-17T09:00:00+08:00",
  "items": [
    {
      "headline": "E2E test headline",
      "summary": "E2E deterministic validation item.",
      "primary_source_url": "https://example.com/e2e",
      "published_at": "2026-06-17T08:00:00+08:00",
      "confidence": "high"
    }
  ]
}
JSON

"$PYTHON" scripts/validate_news_payload.py /tmp/e2e-draft.json --min-items 1 --max-items 8 > /tmp/e2e-validate.json || true
if "$PYTHON" - <<'PY'
import json
d=json.load(open('/tmp/e2e-validate.json'))
raise SystemExit(0 if d.get('ok') else 1)
PY
then
  pass "validate_news_payload"
else
  fail "validate_news_payload"
fi

"$PYTHON" scripts/hash_payload.py /tmp/e2e-draft.json > /tmp/e2e-hash.json
assert_json_ok "hash_payload" /tmp/e2e-hash.json
PAYLOAD_HASH="$("$PYTHON" -c 'import json;print(json.load(open("/tmp/e2e-hash.json"))["sha256"])')"

cat > /tmp/e2e-approval.json <<JSON
{
  "job_id": "$JOB_ID-e2e",
  "payload_hash": "$PAYLOAD_HASH",
  "report_date": "2026-06-17",
  "window_start": "2026-06-16T09:00:00+08:00",
  "window_end": "2026-06-17T09:00:00+08:00",
  "draft_payload": $(cat /tmp/e2e-draft.json),
  "receive_id": "$FEISHU_NEWS_ADMIN_ID",
  "receive_id_type": "open_id",
  "dry_run": true
}
JSON

if LARK_CLI_BIN="${LARK_CLI_BIN:-echo}" "$PYTHON" scripts/send_feishu_approval.py --input /tmp/e2e-approval.json --cli "${LARK_CLI_BIN:-echo}" --dry-run > /tmp/e2e-approval-send.json; then
  assert_json_ok "send_feishu_approval dry-run" /tmp/e2e-approval-send.json
else
  fail "send_feishu_approval dry-run"
fi

cat > /tmp/e2e-callback.json <<JSON
{
  "decision": "approved",
  "job_id": "$JOB_ID-e2e",
  "payload_hash": "$PAYLOAD_HASH",
  "operator_user_id": "$FEISHU_NEWS_ADMIN_ID",
  "expires_at": "2099-01-01T00:00:00+00:00"
}
JSON

"$PYTHON" scripts/validate_feishu_callback.py --input /tmp/e2e-callback.json --expected-job-id "$JOB_ID-e2e" --expected-payload-hash "$PAYLOAD_HASH" --admin-id "$FEISHU_NEWS_ADMIN_ID" --skip-signature-check > /tmp/e2e-callback-validate.json
assert_json_ok "validate_feishu_callback" /tmp/e2e-callback-validate.json

printf '%s\n' '{"records":[{"fields":{"标题":"E2E","摘要":"archive dry-run","Run ID":"'"$JOB_ID-e2e"'"}}]}' | "$PYTHON" scripts/archive_feishu_base.py --dry-run --cli "${LARK_CLI_BIN:-echo}" > /tmp/e2e-archive.json || true
if "$PYTHON" - <<'PY'
import json
d=json.load(open('/tmp/e2e-archive.json'))
raise SystemExit(0 if d.get('ok') else 1)
PY
then
  pass "archive_feishu_base dry-run"
else
  fail "archive_feishu_base dry-run"
fi

cat > /tmp/e2e-archived-records.json <<JSON
{
  "run_context": $(python3 -c 'import json;print(json.dumps(json.load(open("/tmp/e2e-run-context.json"))["run_context"]))'),
  "results": [
    {
      "record_id": "rec_e2e",
      "fields": {
        "日期": "2026-06-17",
        "标题": "E2E test headline",
        "摘要": "E2E deterministic validation item.",
        "意义": "验证卡片构建",
        "来源": "https://example.com/e2e",
        "可信度": "high",
        "分类": "model",
        "Run ID": "$JOB_ID-e2e"
      }
    }
  ]
}
JSON

"$PYTHON" scripts/build_feishu_card.py /tmp/e2e-archived-records.json > /tmp/e2e-card.json
if "$PYTHON" - <<'PY'
import json
d=json.load(open('/tmp/e2e-card.json'))
raise SystemExit(0 if 'card' in d else 1)
PY
then
  pass "build_feishu_card"
else
  fail "build_feishu_card"
fi

"$PYTHON" - <<'PY' > /tmp/e2e-card-message.json
import json
card = json.load(open('/tmp/e2e-card.json', encoding='utf-8'))
print(json.dumps({
  'receive_id_type': 'chat_id',
  'receive_id': 'oc_test',
  'card': card['card'],
  'dry_run': True,
}, ensure_ascii=False))
PY

if LARK_CLI_BIN="${LARK_CLI_BIN:-echo}" "$PYTHON" scripts/send_feishu_card.py --input /tmp/e2e-card-message.json --cli "${LARK_CLI_BIN:-echo}" --dry-run > /tmp/e2e-card-send.json; then
  assert_json_ok "send_feishu_card dry-run" /tmp/e2e-card-send.json
else
  fail "send_feishu_card dry-run"
fi

if command -v openclaw >/dev/null 2>&1; then
  if openclaw skills info ai-news >/tmp/e2e-openclaw-skill.txt 2>&1; then
    if grep -q "ai-news" /tmp/e2e-openclaw-skill.txt; then
      pass "openclaw skill installed"
    else
      fail "openclaw skill installed"
    fi
  else
    skip "openclaw skill installed (openclaw skills info failed)"
  fi
else
  skip "openclaw skill installed (openclaw not in PATH)"
fi

if command -v openclaw >/dev/null 2>&1; then
  if [ "${AI_NEWS_E2E_WECHAT_LIVE:-0}" = "1" ]; then
    if "$PYTHON" scripts/verify_wechat_notify.py --live --message "[ai-news] e2e live wechat notify" > /tmp/e2e-wechat.json; then
      assert_json_ok "wechat notify live" /tmp/e2e-wechat.json
    else
      fail "wechat notify live"
    fi
  else
    if "$PYTHON" scripts/verify_wechat_notify.py > /tmp/e2e-wechat.json; then
      assert_json_ok "wechat notify config" /tmp/e2e-wechat.json
    else
      fail "wechat notify config"
    fi
  fi
else
  skip "wechat notify config (openclaw not in PATH)"
fi

log "summary: pass=$PASS fail=$FAIL skip=$SKIP"
if [ "$FAIL" -gt 0 ]; then
  exit 2
fi
exit 0
