#!/usr/bin/env python3
"""WeChat delivery helpers: pending report staging and session guidance."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PENDING_PATH = Path(
    os.getenv(
        "WEIXIN_PENDING_REPORT",
        str(Path.home() / ".openclaw/workspace/ai-news/reports/weixin-pending.md"),
    )
)

TRIGGER_WORDS = ("发日报", "日报", "早报", "ai-news", "ainews")


def stage_pending_report(report_path: Path, pending_path: Path | None = None) -> dict[str, Any]:
    """Copy the latest report to the WeChat on-demand delivery location."""
    pending = pending_path or DEFAULT_PENDING_PATH
    text = report_path.read_text(encoding="utf-8").strip()
    if not text:
        return {"ok": False, "error": "empty_report"}
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(text + "\n", encoding="utf-8")
    meta_path = pending.with_suffix(".json")
    meta = {
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "source": str(report_path),
        "chars": len(text),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "pending_path": str(pending), "chars": len(text), "meta_path": str(meta_path)}


def load_pending_report(pending_path: Path | None = None) -> str | None:
    pending = pending_path or DEFAULT_PENDING_PATH
    if not pending.exists():
        return None
    text = pending.read_text(encoding="utf-8").strip()
    return text or None


def recent_inbound_minutes(max_age_min: float = 10.0) -> float | None:
    """Return minutes since the latest WeChat inbound message, if found in gateway logs."""
    today = datetime.now().strftime("%Y-%m-%d")
    candidates = [
        Path(f"/tmp/openclaw/openclaw-{today}.log"),
        Path.home() / ".openclaw/logs/gateway.log",
    ]
    latest_ts: float | None = None
    pattern = re.compile(r"inbound message: from=.+@im\.wechat")
    for path in candidates:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-2000:]
        except OSError:
            continue
        for line in lines:
            if not pattern.search(line):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_text = ((payload.get("_meta") or {}).get("date") or payload.get("time") or "")
            if not ts_text:
                continue
            try:
                ts = datetime.fromisoformat(str(ts_text).replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
    if latest_ts is None:
        return None
    age_min = max(0.0, (datetime.now(timezone.utc).timestamp() - latest_ts) / 60.0)
    if age_min > max_age_min:
        return None
    return round(age_min, 1)


def reply_delivery_hint(*, recent_inbound: bool) -> str:
    if recent_inbound:
        return (
            "微信 ilink 主动推送不可用。你刚与 bot 有过对话，请在微信回复「发日报」，"
            "bot 将通过回复链路发送完整日报（已写入 weixin-pending.md）。"
        )
    return (
        "微信 ilink 不支持可靠的定时主动推送。请先给 bot 发任意消息，再回复「发日报」获取完整日报。"
    )
