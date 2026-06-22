"""Shared config loading and routing helpers for AI News source scripts."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPAT_PATH = ROOT / "config" / "agent_reach_compat.yaml"
DEFAULT_POLICY_PATH = ROOT / "config" / "news_channel_policy.yaml"
DEFAULT_HEALTH_SNAPSHOT = Path(
    os.environ.get("AI_NEWS_HEALTH_SNAPSHOT_PATH", "/tmp/ai-news-reach-health.json")
)


def load_simple_yaml(path: Path) -> dict[str, Any]:
    """Load a constrained YAML subset (mappings, lists, scalars) without PyYAML."""
    if not path.exists():
        raise FileNotFoundError(str(path))
    lines = path.read_text(encoding="utf-8").splitlines()
    cleaned: list[str] = []
    for line in lines:
        if "#" in line:
            line = line.split("#", 1)[0]
        cleaned.append(line.rstrip())
    return _parse_mapping(cleaned, 0, 0)[0]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in _split_csv(inner)]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "~"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _split_csv(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_quote: str | None = None
    for ch in text:
        if in_quote:
            current.append(ch)
            if ch == in_quote:
                in_quote = None
            continue
        if ch in {'"', "'"}:
            in_quote = ch
            current.append(ch)
            continue
        if ch == ",":
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return parts


def _parse_mapping(lines: list[str], start: int, base_indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        indent = _indent(line)
        if indent < base_indent:
            break
        if indent > base_indent:
            raise ValueError(f"Unexpected indentation at line {index + 1}")
        stripped = line.strip()
        if stripped.startswith("- "):
            raise ValueError(f"Expected mapping key at line {index + 1}")
        if ":" not in stripped:
            raise ValueError(f"Invalid mapping line at {index + 1}: {stripped}")
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            result[key] = _parse_scalar(raw_value)
            index += 1
            continue
        index += 1
        if index >= len(lines) or not lines[index].strip():
            result[key] = {}
            continue
        child_indent = _indent(lines[index])
        if lines[index].lstrip().startswith("- "):
            items, index = _parse_list(lines, index, child_indent)
            result[key] = items
        else:
            nested, index = _parse_mapping(lines, index, child_indent)
            result[key] = nested
    return result, index


def _parse_list(lines: list[str], start: int, base_indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        indent = _indent(line)
        if indent < base_indent:
            break
        if indent > base_indent:
            break
        stripped = line.strip()
        if not stripped.startswith("- "):
            break
        payload = stripped[2:].strip()
        if not payload:
            index += 1
            if index >= len(lines) or _indent(lines[index]) <= base_indent:
                items.append(None)
                continue
            if lines[index].lstrip().startswith("- "):
                items.append(None)
                continue
            nested, index = _parse_mapping(lines, index, base_indent + 2)
            items.append(nested)
            continue
        if ":" in payload:
            key, raw_value = payload.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            if raw_value:
                items.append({key: _parse_scalar(raw_value)})
                index += 1
                continue
            index += 1
            if index < len(lines) and _indent(lines[index]) > base_indent and not lines[index].lstrip().startswith("- "):
                nested, index = _parse_mapping(lines, index, base_indent + 2)
                items.append({key: nested})
            else:
                items.append({key: {}})
            continue
        items.append(_parse_scalar(payload))
        index += 1
    return items, index


def load_compat(path: Path | None = None) -> dict[str, Any]:
    data = load_simple_yaml(path or DEFAULT_COMPAT_PATH)
    return data.get("agent_reach", data)


def load_policy(path: Path | None = None) -> dict[str, Any]:
    return load_simple_yaml(path or DEFAULT_POLICY_PATH)


def run_command(command: str, timeout: int = 60) -> tuple[int, str, str]:
    completed = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def map_reach_status(status: str) -> str:
    if status == "ok":
        return "healthy"
    if status == "warn":
        return "degraded"
    return "down"


def parse_version_output(stdout: str) -> str | None:
    match = re.search(r"(\d+\.\d+\.\d+)", stdout)
    return match.group(1) if match else None


def version_at_least(current: str | None, minimum: str | None) -> bool:
    if not minimum:
        return True
    if not current:
        return False

    def parts(value: str) -> list[int]:
        return [int(part) for part in value.split(".")]

    cur = parts(current)
    min_parts = parts(minimum)
    length = max(len(cur), len(min_parts))
    cur.extend([0] * (length - len(cur)))
    min_parts.extend([0] * (length - len(min_parts)))
    return cur >= min_parts


def normalize_doctor_channels(doctor_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    channels: dict[str, dict[str, Any]] = {}
    for name, raw in doctor_payload.items():
        if not isinstance(raw, dict):
            continue
        channels[name] = {
            "status": map_reach_status(str(raw.get("status", "error"))),
            "active_backend": raw.get("active_backend"),
            "message": raw.get("message", ""),
            "tier": raw.get("tier"),
            "backends": raw.get("backends", []),
        }
    return channels


def build_routing(
    policy: dict[str, Any],
    reach_channels: dict[str, dict[str, Any]] | None,
    mode_override: str | None = None,
) -> dict[str, Any]:
    topics = policy.get("topics", {})
    coverage_rules = policy.get("coverage_rules", {})
    fallback_channels = policy.get("fallback_channels", ["web", "rss", "exa_search"])
    reach_channels = reach_channels or {}

    allowed: list[str] = []
    degraded: list[str] = []
    blocked: list[str] = []
    coverage_alerts: list[str] = []
    topic_routes: dict[str, dict[str, Any]] = {}

    for topic_name, topic_cfg in topics.items():
        if not isinstance(topic_cfg, dict):
            continue
        primary = [str(ch) for ch in topic_cfg.get("primary_channels", [])]
        requires = [str(ch) for ch in topic_cfg.get("requires_reach_channels", [])]
        route_allowed: list[str] = []
        route_degraded: list[str] = []
        route_blocked: list[str] = []

        for channel in primary:
            health = reach_channels.get(channel, {}).get("status")
            if health == "healthy":
                route_allowed.append(channel)
            elif health == "degraded":
                route_degraded.append(channel)
            elif health is None and channel in {"rss"}:
                route_allowed.append(channel)
            else:
                route_blocked.append(channel)

        optional = not requires or all(ch in route_allowed or ch in route_degraded for ch in requires)
        if requires and not optional:
            missing = [ch for ch in requires if ch not in route_allowed and ch not in route_degraded]
            if missing:
                coverage_alerts.append(f"{topic_name} requires unavailable channels: {', '.join(missing)}")

        topic_routes[topic_name] = {
            "allowed_channels": route_allowed,
            "degraded_channels": route_degraded,
            "blocked_channels": route_blocked,
            "preferred_domains": topic_cfg.get("preferred_domains", []),
            "rss_feeds": topic_cfg.get("rss_feeds", []),
            "optional": optional,
        }

        for channel in route_allowed:
            if channel not in allowed:
                allowed.append(channel)
        for channel in route_degraded:
            if channel not in degraded:
                degraded.append(channel)
        for channel in route_blocked:
            if channel not in blocked:
                blocked.append(channel)

    healthy_primary = [ch for ch in allowed if reach_channels.get(ch, {}).get("status") == "healthy"]
    min_healthy = int(coverage_rules.get("min_healthy_primary_channels", 2))
    mode = "normal"

    if len(healthy_primary) < min_healthy:
        for channel in fallback_channels:
            health = reach_channels.get(channel, {}).get("status")
            if health in {"healthy", "degraded"} and channel not in allowed:
                allowed.append(channel)
            if health == "degraded" and channel not in degraded:
                degraded.append(channel)
            elif health is None and channel == "rss" and channel not in allowed:
                allowed.append(channel)
        healthy_primary = [
            ch
            for ch in allowed
            if reach_channels.get(ch, {}).get("status") == "healthy" or ch == "rss"
        ]

    if mode_override:
        mode = mode_override
        if mode_override == "rss_only" and "rss" not in allowed:
            allowed.append("rss")
    elif len(healthy_primary) < min_healthy and coverage_rules.get("allow_degraded_run", True):
        mode = "degraded"
        coverage_alerts.append(
            f"Only {len(healthy_primary)} healthy primary channels; running in degraded mode"
        )
    elif len(healthy_primary) < min_healthy:
        mode = "rss_only"
        coverage_alerts.append("Insufficient healthy channels; recommend rss_only fallback")

    return {
        "mode": mode,
        "allowed_channels": allowed,
        "degraded_channels": degraded,
        "blocked_channels": blocked,
        "coverage_alerts": coverage_alerts,
        "topic_routes": topic_routes,
        "healthy_primary_count": len(healthy_primary),
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
