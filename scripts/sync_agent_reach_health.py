#!/usr/bin/env python3
"""Sync Agent Reach doctor output into an AI News health snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _news_config import (
    DEFAULT_COMPAT_PATH,
    DEFAULT_HEALTH_SNAPSHOT,
    DEFAULT_POLICY_PATH,
    build_routing,
    load_compat,
    load_policy,
    normalize_doctor_channels,
    parse_version_output,
    run_command,
    utc_now_iso,
    version_at_least,
    write_json,
)


def sync_health(
    compat_path: Path,
    policy_path: Path,
    snapshot_path: Path,
    skip_version_check: bool = False,
) -> dict:
    compat = load_compat(compat_path)
    policy = load_policy(policy_path)
    min_version = str(compat.get("min_version", "")) or None
    health_probe = str(compat.get("health_probe", "agent-reach doctor --json"))

    version_code, version_out, version_err = run_command("agent-reach version", timeout=20)
    agent_reach_version = parse_version_output(version_out or version_err)

    if version_code != 0:
        payload = {
            "ok": False,
            "fallback": "rss_only",
            "checked_at": utc_now_iso(),
            "agent_reach_version": agent_reach_version,
            "error": "agent-reach not available",
            "detail": version_err or version_out or "agent-reach version failed",
            "channels": {},
            "routing": build_routing(policy, {}, mode_override="rss_only"),
            "snapshot_path": str(snapshot_path),
        }
        write_json(snapshot_path, payload)
        return payload

    if not skip_version_check and not version_at_least(agent_reach_version, min_version):
        payload = {
            "ok": False,
            "fallback": "rss_only",
            "checked_at": utc_now_iso(),
            "agent_reach_version": agent_reach_version,
            "error": "agent_reach_version_too_old",
            "detail": f"requires >= {min_version}",
            "channels": {},
            "routing": build_routing(policy, {}, mode_override="rss_only"),
            "snapshot_path": str(snapshot_path),
        }
        write_json(snapshot_path, payload)
        return payload

    doctor_code, doctor_out, doctor_err = run_command(health_probe, timeout=120)
    if doctor_code != 0 or not doctor_out:
        payload = {
            "ok": False,
            "fallback": "rss_only",
            "checked_at": utc_now_iso(),
            "agent_reach_version": agent_reach_version,
            "error": "doctor_failed",
            "detail": doctor_err or doctor_out or "empty doctor output",
            "channels": {},
            "routing": build_routing(policy, {}, mode_override="rss_only"),
            "snapshot_path": str(snapshot_path),
        }
        write_json(snapshot_path, payload)
        return payload

    try:
        doctor_payload = json.loads(doctor_out)
    except json.JSONDecodeError as exc:
        payload = {
            "ok": False,
            "fallback": "rss_only",
            "checked_at": utc_now_iso(),
            "agent_reach_version": agent_reach_version,
            "error": "doctor_json_invalid",
            "detail": str(exc),
            "channels": {},
            "routing": build_routing(policy, {}, mode_override="rss_only"),
            "snapshot_path": str(snapshot_path),
        }
        write_json(snapshot_path, payload)
        return payload

    channels = normalize_doctor_channels(doctor_payload)
    routing = build_routing(policy, channels)
    payload = {
        "ok": True,
        "checked_at": utc_now_iso(),
        "agent_reach_version": agent_reach_version,
        "channels": channels,
        "routing": routing,
        "snapshot_path": str(snapshot_path),
    }
    write_json(snapshot_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compat", default=str(DEFAULT_COMPAT_PATH))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--snapshot", default=str(DEFAULT_HEALTH_SNAPSHOT))
    parser.add_argument("--skip-version-check", action="store_true")
    args = parser.parse_args()

    payload = sync_health(
        Path(args.compat),
        Path(args.policy),
        Path(args.snapshot),
        skip_version_check=args.skip_version_check,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
