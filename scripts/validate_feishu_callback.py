#!/usr/bin/env python3
"""Validate Feishu approval callback: signature, operator, expiry, and payload hash."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any


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


def expected_signature(secret: str, timestamp: str, nonce: str, body_raw: str) -> str:
    message = f"{timestamp}{nonce}{body_raw}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def extract_operator(payload: dict[str, Any]) -> str | None:
    direct = payload.get("operator_user_id")
    if direct:
        return str(direct)
    event = payload.get("event")
    if isinstance(event, dict):
        operator = event.get("operator")
        if isinstance(operator, dict):
            for key in ("open_id", "user_id", "union_id"):
                if operator.get(key):
                    return str(operator[key])
        if event.get("operator_user_id"):
            return str(event.get("operator_user_id"))
    return None


def extract_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("event"), dict):
        event = payload["event"]
        action_value = event.get("action", {}).get("value")
        if isinstance(action_value, dict):
            normalized = dict(action_value)
            normalized.setdefault("feedback", event.get("comment"))
            normalized.setdefault("operator_user_id", extract_operator(payload))
            normalized.setdefault("decided_at", datetime.now(timezone.utc).isoformat())
            return normalized
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Callback JSON file, or stdin when omitted")
    parser.add_argument("--expected-job-id")
    parser.add_argument("--expected-payload-hash")
    parser.add_argument("--admin-id", default=os.getenv("FEISHU_NEWS_ADMIN_ID"))
    parser.add_argument("--admin-id-type", default=os.getenv("FEISHU_NEWS_ADMIN_ID_TYPE", "open_id"))
    parser.add_argument("--app-secret", default=os.getenv("FEISHU_APP_SECRET"))
    parser.add_argument("--header-timestamp")
    parser.add_argument("--header-nonce")
    parser.add_argument("--header-signature")
    parser.add_argument("--raw-body", help="Exact callback raw body used by signature check")
    parser.add_argument("--now", help="Override current time in ISO-8601 for tests")
    parser.add_argument("--skip-signature-check", action="store_true")
    args = parser.parse_args()

    raw_body = args.raw_body
    if raw_body is None:
        raw_body = sys.stdin.read().strip() if not args.input else ""
        payload = json.loads(raw_body) if raw_body else read_json(args.input)
        if not raw_body:
            raw_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    else:
        payload = json.loads(raw_body)

    action_payload = extract_payload(payload)
    decision = str(action_payload.get("decision") or "").strip().lower()
    job_id = str(action_payload.get("job_id") or "")
    payload_hash = str(action_payload.get("payload_hash") or "")
    expires_at = str(action_payload.get("expires_at") or "")
    feedback = action_payload.get("feedback")
    operator_user_id = str(action_payload.get("operator_user_id") or extract_operator(payload) or "")
    decided_at = str(action_payload.get("decided_at") or datetime.now(timezone.utc).isoformat())

    errors: list[str] = []
    checks: dict[str, bool] = {}

    if decision not in {"approved", "rejected"}:
        errors.append("decision must be approved or rejected")
    checks["decision_valid"] = decision in {"approved", "rejected"}

    if args.expected_job_id and job_id != args.expected_job_id:
        errors.append("job_id mismatch")
    checks["job_id_match"] = (not args.expected_job_id) or (job_id == args.expected_job_id)

    if args.expected_payload_hash and payload_hash != args.expected_payload_hash:
        errors.append("payload_hash mismatch")
    checks["payload_hash_match"] = (not args.expected_payload_hash) or (payload_hash == args.expected_payload_hash)

    if args.admin_id and operator_user_id != args.admin_id:
        errors.append("operator_user_id mismatch")
    checks["operator_match"] = (not args.admin_id) or (operator_user_id == args.admin_id)

    now = parse_iso(args.now) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    expiry = parse_iso(expires_at)
    if expiry is None:
        errors.append("expires_at missing or invalid")
        checks["not_expired"] = False
    else:
        checks["not_expired"] = now <= expiry
        if now > expiry:
            errors.append("approval decision is expired")

    signature_valid = True
    if not args.skip_signature_check:
        required_sig = {
            "app_secret": args.app_secret,
            "header_timestamp": args.header_timestamp,
            "header_nonce": args.header_nonce,
            "header_signature": args.header_signature,
        }
        missing_sig = [k for k, v in required_sig.items() if not v]
        if missing_sig:
            signature_valid = False
            errors.append(f"missing signature fields: {', '.join(missing_sig)}")
        else:
            expected = expected_signature(
                secret=str(args.app_secret),
                timestamp=str(args.header_timestamp),
                nonce=str(args.header_nonce),
                body_raw=raw_body,
            )
            signature_valid = hmac.compare_digest(expected, str(args.header_signature))
            if not signature_valid:
                errors.append("signature mismatch")
    checks["signature_valid"] = signature_valid

    ok = not errors
    result = {
        "ok": ok,
        "decision": decision,
        "job_id": job_id,
        "payload_hash": payload_hash,
        "operator_user_id": operator_user_id,
        "admin_id_type": args.admin_id_type,
        "feedback": feedback if decision == "rejected" else None,
        "decided_at": decided_at,
        "checks": checks,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
