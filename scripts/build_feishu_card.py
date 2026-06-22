#!/usr/bin/env python3
"""Build a Feishu interactive card from archived Base record fields."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from typing import Any


def read_json(path: str | None) -> dict[str, Any]:
    if not path or path == "-":
        raw = sys.stdin.read().strip()
        return json.loads(raw) if raw else {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def field(fields: dict[str, Any], name: str, default: str = "") -> str:
    value = fields.get(name, default)
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value)
    return str(value) if value is not None else default


def collect_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("records"), list):
        return payload["records"]
    if isinstance(payload.get("results"), list):
        return payload["results"]
    archive = payload.get("archive_result")
    if isinstance(archive, dict) and isinstance(archive.get("results"), list):
        return archive["results"]
    return []


def record_fields(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields", record)
    return fields if isinstance(fields, dict) else {}


def extract_url(value: str) -> str | None:
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    match = re.search(r"https?://[^\s)>\"]+", value)
    return match.group(0) if match else None


def format_source_link(source: str) -> str:
    source = source.strip()
    if not source:
        return ""
    url = extract_url(source)
    if url:
        return f"[原文链接]({url})"
    return f"来源：{source}"


def build_item_md(index: int, record: dict[str, Any]) -> str:
    fields = record_fields(record)
    title = field(fields, "标题", f"新闻 {index}")
    summary = field(fields, "摘要")
    why = field(fields, "意义")
    source = field(fields, "来源")
    confidence = field(fields, "可信度")
    category = field(fields, "分类")
    record_id = record.get("record_id") or field(fields, "记录 ID")

    lines = [f"**{index}. {title}**"]
    if summary:
        lines.append(f"摘要：{summary}")
    if why:
        lines.append(f"意义：{why}")
    meta = " · ".join(part for part in [category, f"可信度：{confidence}" if confidence else ""] if part)
    if meta:
        lines.append(meta)
    if source:
        lines.append(format_source_link(source))
    if record_id:
        lines.append(f"Base Record：{record_id}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", nargs="?", help="Archived records JSON, or stdin when omitted")
    parser.add_argument("--title", help="Card title")
    parser.add_argument("--template", default="blue", help="Feishu card header template color")
    parser.add_argument("--max-items", type=int, default=8)
    args = parser.parse_args()

    payload = read_json(args.payload)
    records = [record for record in collect_records(payload) if isinstance(record, dict)]
    if not records:
        print(json.dumps({"ok": False, "error": "records are required"}))
        return 2

    run_context = payload.get("run_context", {}) if isinstance(payload.get("run_context"), dict) else {}
    report_date = (
        payload.get("report_date")
        or run_context.get("window_end", "")[:10]
        or datetime.now().date().isoformat()
    )
    mode = (payload.get("mode") or run_context.get("mode") or run_context.get("report_type") or "daily").lower()
    default_title = f"AI 行业周报｜{report_date}" if mode == "weekly" else f"AI 行业日报｜{report_date}"
    title = args.title or payload.get("title") or default_title
    timezone_name = run_context.get("timezone") or payload.get("timezone") or "Asia/Shanghai"
    window_start = run_context.get("window_start") or payload.get("window_start")
    window_end = run_context.get("window_end") or payload.get("window_end")

    elements: list[dict[str, Any]] = []
    if window_start and window_end:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"时间范围：{window_start} - {window_end}（{timezone_name}）\n数据来源：飞书多维表",
                },
            }
        )
    else:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "数据来源：飞书多维表"}})

    for index, record in enumerate(records[: args.max_items], start=1):
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": build_item_md(index, record)}})

    card = {
        "config": {"wide_screen_mode": True},
        "header": {"template": args.template, "title": {"tag": "plain_text", "content": title}},
        "elements": elements,
    }
    print(json.dumps({"ok": True, "card": card, "item_count": min(len(records), args.max_items)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
