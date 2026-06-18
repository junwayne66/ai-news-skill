#!/usr/bin/env python3
"""Fetch RSS/Atom feeds deterministically and emit normalized items."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


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


def parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed_iso = parse_iso(value)
    if parsed_iso:
        return parsed_iso.astimezone(timezone.utc)
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def strip_text(value: str | None) -> str:
    return (value or "").strip()


def safe_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value
    return ""


def stable_id(source_name: str, url: str, guid: str | None = None) -> str:
    native = guid or url
    digest = hashlib.sha256(native.encode("utf-8")).hexdigest()[:16]
    source_slug = source_name.lower().replace(" ", "-")
    return f"rss:{source_slug}:{digest}"


def feed_list_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    feeds = payload.get("feeds")
    if isinstance(feeds, list):
        return [item for item in feeds if isinstance(item, dict)]
    if isinstance(payload.get("sources"), dict) and isinstance(payload["sources"].get("rss"), list):
        return [item for item in payload["sources"]["rss"] if isinstance(item, dict)]
    config = payload.get("config")
    if isinstance(config, dict):
        sources = config.get("sources")
        if isinstance(sources, dict) and isinstance(sources.get("rss"), list):
            return [item for item in sources["rss"] if isinstance(item, dict)]
    return []


def read_url(url: str, timeout_sec: int) -> bytes:
    request = Request(url, headers={"User-Agent": "ai-news-fetch-rss/1.0"})
    with urlopen(request, timeout=timeout_sec) as response:
        return response.read()


def parse_rss_channel(root: ET.Element) -> tuple[str, list[ET.Element]]:
    channel = root.find("./channel")
    if channel is None:
        return "", []
    title = strip_text(channel.findtext("title"))
    return title, list(channel.findall("item"))


def parse_atom_feed(root: ET.Element) -> tuple[str, list[ET.Element]]:
    title = strip_text(root.findtext("atom:title", namespaces=ATOM_NS))
    return title, list(root.findall("atom:entry", namespaces=ATOM_NS))


def rss_item_to_record(item: ET.Element, source_name: str, category: str | None, now_iso: str) -> dict[str, Any] | None:
    title = strip_text(item.findtext("title"))
    link = strip_text(item.findtext("link"))
    guid = strip_text(item.findtext("guid"))
    summary = strip_text(item.findtext("description"))
    published_raw = strip_text(item.findtext("pubDate"))
    author = strip_text(item.findtext("author"))
    url = safe_url(link)
    if not title or not url:
        return None
    published = parse_published(published_raw)
    return {
        "id": stable_id(source_name, url, guid or None),
        "source_type": "rss",
        "headline": title,
        "title": title,
        "url": url,
        "content": summary or None,
        "summary": summary or None,
        "author": author or None,
        "published_at": published.isoformat() if published else None,
        "fetched_at": now_iso,
        "metadata": {
            "feed_name": source_name,
            "category": category or "other",
        },
    }


def atom_item_to_record(item: ET.Element, source_name: str, category: str | None, now_iso: str) -> dict[str, Any] | None:
    title = strip_text(item.findtext("atom:title", namespaces=ATOM_NS))
    link_element = item.find("atom:link[@rel='alternate']", namespaces=ATOM_NS) or item.find("atom:link", namespaces=ATOM_NS)
    link = strip_text(link_element.get("href") if link_element is not None else "")
    guid = strip_text(item.findtext("atom:id", namespaces=ATOM_NS))
    summary = strip_text(item.findtext("atom:summary", namespaces=ATOM_NS) or item.findtext("atom:content", namespaces=ATOM_NS))
    published_raw = strip_text(item.findtext("atom:published", namespaces=ATOM_NS) or item.findtext("atom:updated", namespaces=ATOM_NS))
    author = ""
    author_node = item.find("atom:author", namespaces=ATOM_NS)
    if author_node is not None:
        author = strip_text(author_node.findtext("atom:name", namespaces=ATOM_NS))
    url = safe_url(link)
    if not title or not url:
        return None
    published = parse_published(published_raw)
    return {
        "id": stable_id(source_name, url, guid or None),
        "source_type": "rss",
        "headline": title,
        "title": title,
        "url": url,
        "content": summary or None,
        "summary": summary or None,
        "author": author or None,
        "published_at": published.isoformat() if published else None,
        "fetched_at": now_iso,
        "metadata": {
            "feed_name": source_name,
            "category": category or "other",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="JSON input file, or stdin when omitted")
    parser.add_argument("--since", help="ISO-8601 lower bound; defaults to now-24h")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--timeout-sec", type=int, default=20)
    parser.add_argument("--max-items-per-feed", type=int, default=50)
    args = parser.parse_args()

    payload = read_json(args.input)
    feeds = feed_list_from_payload(payload)
    if not feeds:
        print(json.dumps({"ok": False, "error": "missing_feeds", "hint": "provide feeds[] or config.sources.rss[]"}, ensure_ascii=False))
        return 2

    since = parse_iso(args.since) if args.since else None
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    since = since.astimezone(timezone.utc)
    now_iso = datetime.now(timezone.utc).isoformat()

    items: list[dict[str, Any]] = []
    feed_results: list[dict[str, Any]] = []
    ok = True
    for feed in feeds:
        enabled = bool(feed.get("enabled", True))
        if not enabled:
            continue
        name = str(feed.get("name") or "rss-feed")
        url = str(feed.get("url") or "")
        category = feed.get("category")
        if not safe_url(url):
            ok = False
            feed_results.append({"feed": name, "url": url, "ok": False, "error": "invalid_url"})
            continue
        try:
            raw = read_url(url, args.timeout_sec)
            root = ET.fromstring(raw)
            generated = 0
            if root.tag.endswith("rss") or root.tag.endswith("rdf"):
                _, rss_items = parse_rss_channel(root)
                for node in rss_items:
                    record = rss_item_to_record(node, name, category, now_iso)
                    if not record:
                        continue
                    published = parse_iso(record.get("published_at"))
                    if published and published < since:
                        continue
                    items.append(record)
                    generated += 1
                    if generated >= args.max_items_per_feed:
                        break
            else:
                _, atom_items = parse_atom_feed(root)
                for node in atom_items:
                    record = atom_item_to_record(node, name, category, now_iso)
                    if not record:
                        continue
                    published = parse_iso(record.get("published_at"))
                    if published and published < since:
                        continue
                    items.append(record)
                    generated += 1
                    if generated >= args.max_items_per_feed:
                        break
            feed_results.append({"feed": name, "url": url, "ok": True, "item_count": generated})
        except Exception as exc:
            ok = False
            feed_results.append({"feed": name, "url": url, "ok": False, "error": str(exc)})

    # Partial feed failures are acceptable when at least one feed returned items.
    ok = len(items) > 0
    print(
        json.dumps(
            {
                "ok": ok,
                "source": "rss",
                "since": since.isoformat(),
                "item_count": len(items),
                "items": items,
                "feeds": feed_results,
                "partial": any(not feed.get("ok") for feed in feed_results) and ok,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
