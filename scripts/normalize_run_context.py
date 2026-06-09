#!/usr/bin/env python3
"""Normalize OpenClaw scheduled payloads into a RunContext JSON object."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


REQUIRED_DESTINATION_ENV = [
    "FEISHU_NEWS_ADMIN_ID",
    "FEISHU_GROUP_CHAT_ID",
    "FEISHU_BASE_APP_TOKEN",
    "FEISHU_BASE_TABLE_ID",
]


def parse_iso_datetime(value: str, tz: ZoneInfo) -> datetime:
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def parse_window(value: str) -> timedelta:
    match = re.fullmatch(r"(\d+)([hd])", value.strip().lower())
    if not match:
        raise ValueError("AI_NEWS_WINDOW must look like 24h or 1d")
    amount = int(match.group(1))
    unit = match.group(2)
    return timedelta(hours=amount) if unit == "h" else timedelta(days=amount)


def read_payload(path: str | None) -> dict:
    if not path or path == "-":
        raw = sys.stdin.read().strip()
        return json.loads(raw) if raw else {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def env_or_payload(name: str, payload: dict, default: str | None = None) -> str | None:
    if os.getenv(name):
        return os.getenv(name)
    lower = name.lower()
    if lower in payload:
        return str(payload[lower])
    if name in payload:
        return str(payload[name])
    return default


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", help="Path to platform payload JSON, or '-' for stdin")
    args = parser.parse_args()

    payload = read_payload(args.payload)
    platform = env_or_payload("AI_NEWS_PLATFORM", payload, "openclaw")
    if platform != "openclaw":
        print(json.dumps({"ok": False, "error": "AI_NEWS_PLATFORM must be openclaw"}))
        return 2

    timezone_name = env_or_payload("AI_NEWS_TIMEZONE", payload, "Asia/Shanghai")
    tz = ZoneInfo(timezone_name)

    scheduled_raw = (
        payload.get("scheduled_at")
        or payload.get("triggered_at")
        or payload.get("time")
        or datetime.now(timezone.utc).isoformat()
    )
    scheduled_at = parse_iso_datetime(str(scheduled_raw), tz)
    window_delta = parse_window(env_or_payload("AI_NEWS_WINDOW", payload, "24h") or "24h")
    window_start = scheduled_at - window_delta

    missing = [name for name in REQUIRED_DESTINATION_ENV if not env_or_payload(name, payload)]
    if missing:
        print(json.dumps({"ok": False, "error": "missing_required_fields", "fields": missing}, ensure_ascii=False))
        return 2

    local_date = scheduled_at.date().isoformat()
    timezone_slug = timezone_name.lower().replace("/", "-").replace("_", "-")
    job_id = payload.get("job_id") or f"ai-news-{local_date}-{timezone_slug}"

    context = {
        "job_id": job_id,
        "platform": platform,
        "trigger_type": payload.get("trigger_type", "scheduled"),
        "scheduled_at": scheduled_at.isoformat(),
        "window_start": window_start.isoformat(),
        "window_end": scheduled_at.isoformat(),
        "timezone": timezone_name,
        "attempt": int(payload.get("attempt", os.getenv("AI_NEWS_ATTEMPT", "1"))),
        "max_attempts": int(payload.get("max_attempts", os.getenv("AI_NEWS_MAX_ATTEMPTS", "3"))),
        "trace_id": str(payload.get("trace_id", payload.get("run_id", job_id))),
        "max_items": int(env_or_payload("AI_NEWS_MAX_ITEMS", payload, "8") or "8"),
        "language": env_or_payload("AI_NEWS_LANGUAGE", payload, "zh-CN"),
        "approval_user_id": env_or_payload("FEISHU_NEWS_ADMIN_ID", payload),
        "publish_chat_id": env_or_payload("FEISHU_GROUP_CHAT_ID", payload),
        "base_app_token": env_or_payload("FEISHU_BASE_APP_TOKEN", payload),
        "base_table_id": env_or_payload("FEISHU_BASE_TABLE_ID", payload),
    }
    print(json.dumps({"ok": True, "run_context": context}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
