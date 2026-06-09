#!/usr/bin/env python3
"""Archive records to Feishu/Lark Base through lark-cli raw API."""

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


def extract_record_id(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    if isinstance(data, dict):
        record = data.get("record")
        if isinstance(record, dict):
            return record.get("record_id") or record.get("id")
        if data.get("record_id"):
            return data.get("record_id")
    return response.get("record_id")


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
    records = payload.get("records", [])
    if not isinstance(records, list):
        print(json.dumps({"ok": False, "error": "records must be a list"}))
        return 2

    missing = [
        name
        for name, value in {
            "app_token": args.app_token,
            "table_id": args.table_id,
            "records": records,
        }.items()
        if not value
    ]
    if missing:
        print(json.dumps({"ok": False, "error": "missing_required_fields", "fields": missing}))
        return 2

    endpoint = f"/open-apis/bitable/v1/apps/{args.app_token}/tables/{args.table_id}/records"
    results = []
    ok = True
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            results.append({"index": index, "ok": False, "error": "record must be an object"})
            ok = False
            continue
        fields = record.get("fields", record)
        if not isinstance(fields, dict):
            results.append({"index": index, "ok": False, "error": "record fields must be an object"})
            ok = False
            continue

        command = [
            args.cli,
            "api",
            "POST",
            endpoint,
            "--data",
            json.dumps({"fields": fields}, ensure_ascii=False, separators=(",", ":")),
            "--format",
            "json",
        ]
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
                "returncode": result.returncode,
                "record_id": extract_record_id(stdout_json),
                "fields": fields,
                "stdout_json": stdout_json,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )

    print(json.dumps({"ok": ok, "dry_run": args.dry_run, "results": results}, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
