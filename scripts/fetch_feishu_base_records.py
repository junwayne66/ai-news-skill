#!/usr/bin/env python3
"""Fetch Feishu/Lark Base records by record_id through lark-cli raw API."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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


def collect_record_ids(payload: dict[str, Any]) -> list[str]:
    if isinstance(payload.get("record_ids"), list):
        return [str(record_id) for record_id in payload["record_ids"] if record_id]
    ids: list[str] = []
    for key in ("records", "results"):
        values = payload.get(key)
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict) and item.get("record_id"):
                    ids.append(str(item["record_id"]))
    archive = payload.get("archive_result")
    if isinstance(archive, dict):
        ids.extend(collect_record_ids(archive))
    return list(dict.fromkeys(ids))


def extract_fields(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    data = response.get("data")
    if isinstance(data, dict):
        record = data.get("record")
        if isinstance(record, dict) and isinstance(record.get("fields"), dict):
            return record["fields"]
        if isinstance(data.get("fields"), dict):
            return data["fields"]
    if isinstance(response.get("fields"), dict):
        return response["fields"]
    return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="JSON input file, or stdin when omitted")
    parser.add_argument("--app-token", default=os.getenv("FEISHU_BASE_APP_TOKEN"))
    parser.add_argument("--table-id", default=os.getenv("FEISHU_BASE_TABLE_ID"))
    parser.add_argument("--as", dest="as_identity", default=os.getenv("LARK_CLI_AS", "bot"))
    parser.add_argument("--cli", default=os.getenv("LARK_CLI_BIN", "lark-cli"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = read_json(args.input)
    record_ids = collect_record_ids(payload)
    missing = [
        name
        for name, value in {
            "app_token": args.app_token,
            "table_id": args.table_id,
            "record_ids": record_ids,
        }.items()
        if not value
    ]
    if missing:
        print(json.dumps({"ok": False, "error": "missing_required_fields", "fields": missing}))
        return 2

    results = []
    ok = True
    for index, record_id in enumerate(record_ids, start=1):
        endpoint = f"/open-apis/bitable/v1/apps/{args.app_token}/tables/{args.table_id}/records/{record_id}"
        command = [args.cli, "api", "GET", endpoint, "--format", "json"]
        if args.as_identity:
            command.extend(["--as", str(args.as_identity)])
        if args.dry_run:
            command.append("--dry-run")

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        stdout_json = maybe_json(result.stdout.strip()) if result.stdout.strip() else None
        item_ok = result.returncode == 0
        ok = ok and item_ok
        results.append(
            {
                "index": index,
                "ok": item_ok,
                "record_id": record_id,
                "fields": extract_fields(stdout_json),
                "returncode": result.returncode,
                "stdout_json": stdout_json,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )

    print(json.dumps({"ok": ok, "dry_run": args.dry_run, "results": results}, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
