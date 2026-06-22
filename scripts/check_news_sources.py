#!/usr/bin/env python3
"""Check AI News source health by combining Agent Reach channels and RSS probes."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from _news_config import (
    DEFAULT_HEALTH_SNAPSHOT,
    DEFAULT_POLICY_PATH,
    build_routing,
    load_policy,
    read_json,
    utc_now_iso,
    write_json,
)
from sync_agent_reach_health import sync_health


def probe_url(url: str, timeout: int = 10) -> tuple[str, int | None, str | None]:
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "ai-news-source-check/1.0"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            latency_ms = int((time.monotonic() - started) * 1000)
            if response.status >= 400:
                return "down", latency_ms, f"HTTP {response.status}"
            return "healthy", latency_ms, None
    except urllib.error.HTTPError as exc:
        if exc.code in {403, 405, 501}:
            return probe_get(url, timeout)
        latency_ms = int((time.monotonic() - started) * 1000)
        return "down", latency_ms, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - report probe failures structurally
        latency_ms = int((time.monotonic() - started) * 1000)
        return "down", latency_ms, str(exc)


def probe_get(url: str, timeout: int) -> tuple[str, int | None, str | None]:
    request = urllib.request.Request(url, headers={"User-Agent": "ai-news-source-check/1.0"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            latency_ms = int((time.monotonic() - started) * 1000)
            if response.status >= 400:
                return "down", latency_ms, f"HTTP {response.status}"
            return "healthy", latency_ms, None
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.monotonic() - started) * 1000)
        return "down", latency_ms, str(exc)


def collect_rss_sources(policy: dict) -> list[dict[str, str]]:
    feeds: list[dict[str, str]] = []
    for topic_name, topic_cfg in policy.get("topics", {}).items():
        if not isinstance(topic_cfg, dict):
            continue
        rss_feeds = topic_cfg.get("rss_feeds", {})
        if isinstance(rss_feeds, dict):
            for feed_id, feed_url in rss_feeds.items():
                feeds.append({"id": str(feed_id), "url": str(feed_url), "topic": str(topic_name)})
    return feeds


def check_sources(
    policy_path: Path,
    snapshot_path: Path,
    refresh_reach: bool,
    probe_timeout: int,
) -> dict:
    policy = load_policy(policy_path)
    if refresh_reach or not snapshot_path.exists():
        reach_payload = sync_health(
            compat_path=Path(__file__).resolve().parents[1] / "config" / "agent_reach_compat.yaml",
            policy_path=policy_path,
            snapshot_path=snapshot_path,
            skip_version_check=False,
        )
    else:
        reach_payload = read_json(snapshot_path)

    reach_channels = reach_payload.get("channels", {})
    mode_override = reach_payload.get("fallback") if not reach_payload.get("ok") else None
    routing = reach_payload.get("routing") or build_routing(policy, reach_channels, mode_override=mode_override)
    source_results = []
    for feed in collect_rss_sources(policy):
        status, latency_ms, error = probe_url(feed["url"], timeout=probe_timeout)
        source_results.append(
            {
                "id": feed["id"],
                "topic": feed["topic"],
                "url": feed["url"],
                "status": status,
                "latency_ms": latency_ms,
                "last_error": error,
            }
        )

    down_feeds = [item["id"] for item in source_results if item["status"] != "healthy"]
    coverage_alerts = list(routing.get("coverage_alerts", []))
    if down_feeds:
        coverage_alerts.append(f"RSS feeds down: {', '.join(down_feeds)}")

    ok = bool(reach_payload.get("ok")) or routing.get("mode") in {"degraded", "rss_only"}
    payload = {
        "ok": ok,
        "checked_at": utc_now_iso(),
        "reach": reach_payload,
        "sources": source_results,
        "routing": routing,
        "coverage_alerts": coverage_alerts,
        "snapshot_path": str(snapshot_path),
    }
    write_json(snapshot_path.with_name("ai-news-source-check.json"), payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--snapshot", default=str(DEFAULT_HEALTH_SNAPSHOT))
    parser.add_argument("--refresh-reach", action="store_true")
    parser.add_argument("--probe-timeout", type=int, default=10)
    args = parser.parse_args()

    payload = check_sources(
        policy_path=Path(args.policy),
        snapshot_path=Path(args.snapshot),
        refresh_reach=args.refresh_reach,
        probe_timeout=args.probe_timeout,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
