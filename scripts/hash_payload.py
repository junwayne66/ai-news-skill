#!/usr/bin/env python3
"""Compute a stable SHA-256 hash for approval or publish payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys


def read_input(path: str | None) -> str:
    if not path or path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def canonicalize(raw: str) -> str:
    stripped = raw.strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", nargs="?", help="Payload file, or stdin when omitted")
    args = parser.parse_args()

    canonical = canonicalize(read_input(args.payload))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    print(json.dumps({"ok": True, "sha256": digest, "canonical_bytes": len(canonical.encode("utf-8"))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
