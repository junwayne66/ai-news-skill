#!/usr/bin/env python3
"""Validate a Feishu-ready AI news payload before archive and publish."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from urllib.parse import urlparse


REQUIRED_TOP_LEVEL = ["report_date", "timezone", "window_start", "window_end", "items"]
REQUIRED_ITEM_FIELDS = ["headline", "summary", "primary_source_url", "published_at", "confidence"]
VALID_CONFIDENCE = {"high", "medium", "low", "高", "中", "低"}


def read_payload(path: str | None) -> dict:
    if not path or path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_dt(value: str, field: str, errors: list[str]) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        errors.append(f"{field} must be ISO-8601 datetime")
        return None


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", nargs="?", help="Draft payload JSON, or stdin when omitted")
    parser.add_argument("--min-items", type=int, default=5)
    parser.add_argument("--max-items", type=int, default=8)
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    payload = read_payload(args.payload)

    for field in REQUIRED_TOP_LEVEL:
        if field not in payload:
            errors.append(f"missing top-level field: {field}")

    window_start = parse_dt(str(payload.get("window_start", "")), "window_start", errors) if "window_start" in payload else None
    window_end = parse_dt(str(payload.get("window_end", "")), "window_end", errors) if "window_end" in payload else None
    if window_start and window_end and window_start >= window_end:
        errors.append("window_start must be before window_end")

    items = payload.get("items", [])
    if not isinstance(items, list):
        errors.append("items must be a list")
        items = []

    if len(items) < args.min_items:
        errors.append(f"items must contain at least {args.min_items} entries")
    if len(items) > args.max_items:
        errors.append(f"items must contain at most {args.max_items} entries")

    seen_urls: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"item {index} must be an object")
            continue
        for field in REQUIRED_ITEM_FIELDS:
            if not item.get(field):
                errors.append(f"item {index} missing field: {field}")
        url = str(item.get("primary_source_url", ""))
        if url:
            if not valid_url(url):
                errors.append(f"item {index} primary_source_url is invalid")
            if url in seen_urls:
                errors.append(f"item {index} duplicates a primary_source_url")
            seen_urls.add(url)
        confidence = str(item.get("confidence", ""))
        if confidence and confidence not in VALID_CONFIDENCE:
            errors.append(f"item {index} confidence must be high/medium/low or 高/中/低")
        published = item.get("published_at")
        if published:
            published_dt = parse_dt(str(published), f"item {index} published_at", errors)
            if published_dt and window_start and window_end:
                if not (window_start <= published_dt <= window_end):
                    warnings.append(f"item {index} published_at is outside the report window")
        summary = str(item.get("summary", ""))
        if len(summary) > 500:
            warnings.append(f"item {index} summary is longer than 500 characters")

    result = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "item_count": len(items),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
