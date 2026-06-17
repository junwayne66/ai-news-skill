#!/usr/bin/env python3
"""Fetch configured deterministic sources (RSS, Hacker News) and merge results."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent


def read_json(path: str | None) -> dict[str, Any]:
    if not path or path == "-":
        raw = sys.stdin.read().strip()
        return json.loads(raw) if raw else {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def load_config(payload: dict[str, Any], config_path: str | None) -> dict[str, Any]:
    if isinstance(payload.get("config"), dict):
        return payload["config"]
    path = config_path or payload.get("config_path") or os.getenv("AI_NEWS_CONFIG", "data/config.json")
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    if not candidate.exists():
        raise FileNotFoundError(f"config not found: {candidate}")
    return json.loads(candidate.read_text(encoding="utf-8"))


def since_from_context(payload: dict[str, Any], hours: int) -> str:
    run_context = payload.get("run_context") if isinstance(payload.get("run_context"), dict) else {}
    window_start = run_context.get("window_start") or payload.get("window_start")
    if window_start:
        parsed = parse_iso(str(window_start))
        if parsed:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def run_fetch_script(name: str, config_input: str, extra_args: list[str]) -> dict[str, Any]:
    command = [sys.executable, str(SCRIPT_DIR / name), "--input", "-", *extra_args]
    proc = subprocess.run(command, input=config_input, capture_output=True, text=True, check=False)
    if not proc.stdout.strip():
        return {
            "ok": False,
            "script": name,
            "returncode": proc.returncode,
            "error": proc.stderr.strip() or "empty stdout",
            "items": [],
        }
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "script": name,
            "returncode": proc.returncode,
            "error": "invalid json stdout",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "items": [],
        }
    payload["script"] = name
    payload["returncode"] = proc.returncode
    if proc.returncode != 0 and payload.get("ok") is not False:
        payload["ok"] = False
    return payload


def rss_enabled(config: dict[str, Any]) -> bool:
    sources = config.get("sources", {})
    feeds = sources.get("rss", [])
    if not isinstance(feeds, list):
        return False
    return any(isinstance(feed, dict) and feed.get("enabled", True) for feed in feeds)


def hackernews_enabled(config: dict[str, Any]) -> bool:
    sources = config.get("sources", {})
    hn = sources.get("hackernews", {})
    if not isinstance(hn, dict):
        return False
    return bool(hn.get("enabled", True))


def to_collector_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in items:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        candidates.append(
            {
                "id": item.get("id"),
                "headline": item.get("headline") or item.get("title"),
                "raw_summary": item.get("summary") or item.get("content"),
                "primary_source_url": item.get("url"),
                "published_at": item.get("published_at"),
                "source_name": metadata.get("feed_name") or item.get("source_type"),
                "category_guess": metadata.get("category", "other"),
                "why_candidate": f"deterministic fetch from {item.get('source_type')}",
                "prefetched": True,
            }
        )
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="JSON input with optional run_context/config_path")
    parser.add_argument("--config", help="Path to config JSON; defaults to data/config.json")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--timeout-sec", type=int, default=20)
    parser.add_argument("--include-collector-candidates", action="store_true")
    args = parser.parse_args()

    payload = read_json(args.input)
    try:
        config = load_config(payload, args.config)
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    since = since_from_context(payload, args.hours)
    source_runs: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    ok = True

    config_input = json.dumps({"config": config}, ensure_ascii=False)
    common_args = ["--since", since, "--timeout-sec", str(args.timeout_sec)]

    if rss_enabled(config):
        rss_result = run_fetch_script("fetch_rss.py", config_input, common_args)
        source_runs.append(rss_result)
        if not rss_result.get("ok", False):
            ok = False
        items.extend(rss_result.get("items", []))

    if hackernews_enabled(config):
        hn_result = run_fetch_script("fetch_hackernews.py", config_input, common_args)
        source_runs.append(hn_result)
        if not hn_result.get("ok", False):
            ok = False
        items.extend(hn_result.get("items", []))

    if not source_runs:
        print(json.dumps({"ok": False, "error": "no_enabled_deterministic_sources"}, ensure_ascii=False))
        return 2

    output: dict[str, Any] = {
        "ok": ok,
        "since": since,
        "item_count": len(items),
        "items": items,
        "sources": source_runs,
        "enabled_sources": [run.get("script") for run in source_runs],
    }
    if args.include_collector_candidates:
        output["collector_candidates"] = to_collector_candidates(items)

    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
