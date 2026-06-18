#!/usr/bin/env python3
"""Send Feishu approval interactive card with frozen payload metadata."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any


def read_json(path: str | None) -> dict[str, Any]:
    if not path or path == "-":
        raw = sys.stdin.read().strip()
        return json.loads(raw) if raw else {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def maybe_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def iso_now() -> datetime:
    return datetime.now(timezone.utc)


def default_expires(hours: int) -> str:
    return (iso_now() + timedelta(hours=hours)).isoformat()


def build_card(
    title: str,
    report_date: str,
    window_start: str,
    window_end: str,
    timezone_name: str,
    payload_hash: str,
    item_count: int,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    preview = compact_json(metadata.get("draft_preview") or {})
    if len(preview) > 1200:
        preview = preview[:1197] + "..."

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"**日期**：{report_date}\n"
                    f"**时间范围**：{window_start} - {window_end}（{timezone_name}）\n"
                    f"**候选条目数**：{item_count}\n"
                    f"**payload_hash**：`{payload_hash}`"
                ),
            },
            {"tag": "hr"},
            {"tag": "markdown", "content": f"```json\n{preview}\n```"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "同意发布"},
                        "type": "primary",
                        "value": {"decision": "approved", **metadata},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "驳回重写"},
                        "type": "danger",
                        "value": {"decision": "rejected", **metadata},
                    },
                ],
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="JSON input file, or stdin when omitted")
    parser.add_argument("--job-id")
    parser.add_argument("--payload-hash")
    parser.add_argument("--report-date")
    parser.add_argument("--window-start")
    parser.add_argument("--window-end")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--expires-at", help="ISO-8601 expires timestamp")
    parser.add_argument("--expires-in-hours", type=int, default=12)
    parser.add_argument("--receive-id", default=os.getenv("FEISHU_NEWS_ADMIN_ID"))
    parser.add_argument("--receive-id-type", default=os.getenv("FEISHU_NEWS_ADMIN_ID_TYPE", "open_id"))
    parser.add_argument("--title", default="AI 行业日报审批")
    parser.add_argument("--as", dest="as_identity", default=os.getenv("LARK_CLI_AS", "bot"))
    parser.add_argument("--cli", default=os.getenv("LARK_CLI_BIN", "lark-cli"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = read_json(args.input)
    draft_payload = payload.get("draft_payload") if isinstance(payload.get("draft_payload"), dict) else payload
    job_id = args.job_id or payload.get("job_id")
    payload_hash = args.payload_hash or payload.get("payload_hash")
    report_date = args.report_date or payload.get("report_date") or draft_payload.get("report_date") or iso_now().date().isoformat()
    window_start = args.window_start or payload.get("window_start") or draft_payload.get("window_start") or ""
    window_end = args.window_end or payload.get("window_end") or draft_payload.get("window_end") or ""
    timezone_name = args.timezone or payload.get("timezone") or draft_payload.get("timezone") or "Asia/Shanghai"
    expires_at = args.expires_at or payload.get("expires_at") or default_expires(args.expires_in_hours)
    receive_id = args.receive_id or payload.get("receive_id")
    receive_id_type = args.receive_id_type or payload.get("receive_id_type")
    as_identity = payload.get("as") or args.as_identity
    dry_run = args.dry_run or bool(payload.get("dry_run"))

    items = draft_payload.get("items", []) if isinstance(draft_payload.get("items"), list) else []
    item_count = len(items)

    missing = [
        name
        for name, value in {
            "job_id": job_id,
            "payload_hash": payload_hash,
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
        }.items()
        if not value
    ]
    if missing:
        print(json.dumps({"ok": False, "error": "missing_required_fields", "fields": missing}, ensure_ascii=False))
        return 2

    metadata = {
        "action": "ai_news_approval",
        "job_id": str(job_id),
        "payload_hash": str(payload_hash),
        "expires_at": str(expires_at),
        "timezone": timezone_name,
        "draft_preview": {
            "report_date": report_date,
            "item_count": item_count,
            "headlines": [str(item.get("headline", "")) for item in items[:8]],
        },
    }
    card = build_card(
        title=args.title,
        report_date=report_date,
        window_start=window_start,
        window_end=window_end,
        timezone_name=timezone_name,
        payload_hash=str(payload_hash),
        item_count=item_count,
        metadata=metadata,
    )

    params = {"receive_id_type": receive_id_type}
    data = {
        "receive_id": receive_id,
        "msg_type": "interactive",
        "content": compact_json(card),
    }
    command = [
        args.cli,
        "api",
        "POST",
        "/open-apis/im/v1/messages",
        "--params",
        compact_json(params),
        "--data",
        compact_json(data),
        "--format",
        "json",
    ]
    if as_identity:
        command.extend(["--as", str(as_identity)])
    if dry_run:
        command.append("--dry-run")

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    stdout_json = maybe_json(result.stdout.strip()) if result.stdout.strip() else None
    print(
        json.dumps(
            {
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "dry_run": dry_run,
                "approval_metadata": {k: metadata[k] for k in ("action", "job_id", "payload_hash", "expires_at")},
                "card": card,
                "stdout_json": stdout_json,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result.returncode == 0 else result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
