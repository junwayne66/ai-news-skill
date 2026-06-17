#!/usr/bin/env python3
"""Merge cross-source duplicate items by normalized URL (Horizon-style)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.parse import urlparse


def read_json(path: str | None) -> dict[str, Any]:
    if not path or path == "-":
        raw = sys.stdin.read().strip()
        return json.loads(raw) if raw else {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    return f"{host}{path}"


def merge_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        url = str(item.get("url") or item.get("primary_source_url") or "")
        if not url:
            continue
        key = normalize_url(url)
        groups.setdefault(key, []).append(item)

    merged: list[dict[str, Any]] = []
    removed = 0
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        removed += len(group) - 1
        primary = max(group, key=lambda item: len(str(item.get("content") or item.get("summary") or "")))
        metadata = dict(primary.get("metadata") or {})
        merged_sources = set(metadata.get("merged_sources", []))
        for item in group:
            source_type = str(item.get("source_type") or "unknown")
            merged_sources.add(source_type)
            item_meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            for key, value in item_meta.items():
                if key not in metadata or not metadata.get(key):
                    metadata[key] = value
            if item is not primary:
                extra = str(item.get("content") or item.get("summary") or "").strip()
                if extra and extra not in str(primary.get("content") or ""):
                    primary_content = str(primary.get("content") or "")
                    suffix = f"\n\n--- From {source_type} ---\n{extra}"
                    primary["content"] = (primary_content + suffix).strip()
        metadata["merged_sources"] = sorted(merged_sources)
        primary["metadata"] = metadata
        merged.append(primary)

    no_url_items = [item for item in items if not str(item.get("url") or item.get("primary_source_url") or "")]
    merged.extend(no_url_items)
    return merged, removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="JSON with items[] or fetch_sources output")
    args = parser.parse_args()

    payload = read_json(args.input)
    items = payload.get("items", [])
    if not isinstance(items, list):
        print(json.dumps({"ok": False, "error": "items must be a list"}, ensure_ascii=False))
        return 2

    merged, removed = merge_items([item for item in items if isinstance(item, dict)])
    print(
        json.dumps(
            {
                "ok": True,
                "input_count": len(items),
                "item_count": len(merged),
                "removed_duplicates": removed,
                "items": merged,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
