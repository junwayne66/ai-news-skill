#!/usr/bin/env python3
"""Fetch Hacker News items deterministically and emit normalized items."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://hacker-news.firebaseio.com/v0"


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


def safe_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value
    return ""


def get_json(url: str, timeout_sec: int) -> Any:
    request = Request(url, headers={"User-Agent": "ai-news-fetch-hackernews/1.0"})
    with urlopen(request, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def item_url(item: dict[str, Any]) -> str:
    if safe_url(str(item.get("url") or "")):
        return str(item["url"])
    item_id = item.get("id")
    return f"https://news.ycombinator.com/item?id={item_id}"


def normalize_item(item: dict[str, Any], fetched_at: str) -> dict[str, Any]:
    published_ts = int(item.get("time") or 0)
    published = datetime.fromtimestamp(published_ts, tz=timezone.utc).isoformat() if published_ts else None
    score = int(item.get("score") or 0)
    descendants = int(item.get("descendants") or 0)
    title = str(item.get("title") or "").strip()
    url = item_url(item)
    author = str(item.get("by") or "")
    item_id = item.get("id")
    return {
        "id": f"hackernews:story:{item_id}",
        "source_type": "hackernews",
        "headline": title,
        "title": title,
        "url": url,
        "content": item.get("text"),
        "summary": None,
        "author": author or None,
        "published_at": published,
        "fetched_at": fetched_at,
        "metadata": {
            "hn_id": item_id,
            "hn_score": score,
            "hn_comments": descendants,
            "category": "other",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="JSON input file, or stdin when omitted")
    parser.add_argument("--since", help="ISO-8601 lower bound; defaults to now-24h")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--fetch-top-stories", type=int, default=30)
    parser.add_argument("--min-score", type=int, default=100)
    parser.add_argument("--timeout-sec", type=int, default=15)
    parser.add_argument("--include-ask", action="store_true", help="Include ask_hn/job stories; default only 'story'")
    args = parser.parse_args()

    payload = read_json(args.input)
    config = payload.get("hackernews") if isinstance(payload.get("hackernews"), dict) else payload.get("config", {}).get("sources", {}).get("hackernews", {})
    if not isinstance(config, dict):
        config = {}

    fetch_top_stories = int(payload.get("fetch_top_stories") or config.get("fetch_top_stories") or args.fetch_top_stories)
    min_score = int(payload.get("min_score") or config.get("min_score") or args.min_score)
    include_ask = bool(payload.get("include_ask", args.include_ask))

    since = parse_iso(args.since) if args.since else None
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    since = since.astimezone(timezone.utc)

    fetched_at = datetime.now(timezone.utc).isoformat()
    errors: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    ok = True

    try:
        story_ids = get_json(f"{BASE_URL}/topstories.json", args.timeout_sec)
        if not isinstance(story_ids, list):
            raise ValueError("topstories response must be a list")
        for story_id in story_ids[:fetch_top_stories]:
            try:
                item = get_json(f"{BASE_URL}/item/{story_id}.json", args.timeout_sec)
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "story" and not include_ask:
                    continue
                score = int(item.get("score") or 0)
                if score < min_score:
                    continue
                published_ts = int(item.get("time") or 0)
                if published_ts <= 0:
                    continue
                published = datetime.fromtimestamp(published_ts, tz=timezone.utc)
                if published < since:
                    continue
                title = str(item.get("title") or "").strip()
                if not title:
                    continue
                items.append(normalize_item(item, fetched_at))
            except Exception as exc:
                ok = False
                errors.append({"id": story_id, "error": str(exc)})
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "source": "hackernews"}, ensure_ascii=False))
        return 2

    print(
        json.dumps(
            {
                "ok": ok,
                "source": "hackernews",
                "since": since.isoformat(),
                "item_count": len(items),
                "items": items,
                "errors": errors,
                "filters": {
                    "fetch_top_stories": fetch_top_stories,
                    "min_score": min_score,
                    "include_ask": include_ask,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
