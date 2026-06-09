#!/usr/bin/env python3
"""Send a Feishu interactive card through lark-cli raw API."""

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="JSON input file, or stdin when omitted")
    parser.add_argument("--receive-id")
    parser.add_argument("--receive-id-type", default=os.getenv("FEISHU_RECEIVE_ID_TYPE", "chat_id"))
    parser.add_argument("--as", dest="as_identity", default=os.getenv("LARK_CLI_AS", "bot"))
    parser.add_argument("--cli", default=os.getenv("LARK_CLI_BIN", "lark-cli"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = read_json(args.input)
    receive_id = args.receive_id or payload.get("receive_id")
    receive_id_type = args.receive_id_type or payload.get("receive_id_type")
    card = payload.get("card")
    as_identity = payload.get("as") or args.as_identity
    dry_run = args.dry_run or bool(payload.get("dry_run"))

    missing = [
        name
        for name, value in {
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
            "card": card,
        }.items()
        if not value
    ]
    if missing:
        print(json.dumps({"ok": False, "error": "missing_required_fields", "fields": missing}))
        return 2
    if not isinstance(card, dict):
        print(json.dumps({"ok": False, "error": "card must be an object"}))
        return 2

    params = {"receive_id_type": receive_id_type}
    data = {
        "receive_id": receive_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False, separators=(",", ":")),
    }
    command = [
        args.cli,
        "api",
        "POST",
        "/open-apis/im/v1/messages",
        "--params",
        json.dumps(params, ensure_ascii=False, separators=(",", ":")),
        "--data",
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        "--format",
        "json",
    ]
    if as_identity:
        command.extend(["--as", str(as_identity)])
    if dry_run:
        command.append("--dry-run")

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    stdout_json = maybe_json(result.stdout.strip()) if result.stdout.strip() else None
    output = {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_json": stdout_json,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "dry_run": dry_run,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if result.returncode == 0 else result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
