#!/usr/bin/env python3
"""WeChat (openclaw-weixin) helpers: chunking, send, delivery verification."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_MAX_CHARS = int(os.getenv("WEIXIN_CHUNK_MAX_CHARS", "1500"))
MESSAGE_ITEM_RE = re.compile(r"^\d+\.\s", re.MULTILINE)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def openclaw_bin() -> str:
    for candidate in (
        os.getenv("OPENCLAW_BIN"),
        str(Path.home() / ".openclaw/bin/openclaw"),
        str(Path.home() / ".openclaw/tools/node-v22.22.0/bin/openclaw"),
        "openclaw",
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return "openclaw"


def gateway_log_path() -> Path | None:
    today = datetime.now().strftime("%Y-%m-%d")
    candidates = [
        Path(f"/tmp/openclaw/openclaw-{today}.log"),
        Path.home() / ".openclaw/logs/gateway.log",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def split_message(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # Prefer splitting daily reports by numbered news items.
    if MESSAGE_ITEM_RE.search(text):
        return _split_daily_report(text, max_chars)

    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(line) > max_chars:
            chunks.append(line[:max_chars])
            line = line[max_chars:]
        current = line
    if current:
        chunks.append(current)
    return chunks


def _split_daily_report(text: str, max_chars: int) -> list[str]:
    lines = text.splitlines()
    header: list[str] = []
    items: list[str] = []
    footer: list[str] = []
    mode = "header"

    for line in lines:
        if line.startswith("今日关注："):
            mode = "footer"
        if mode == "header":
            if MESSAGE_ITEM_RE.match(line):
                mode = "items"
                items.append(line)
            else:
                header.append(line)
        elif mode == "items":
            if line.startswith("今日关注："):
                mode = "footer"
                footer.append(line)
            elif MESSAGE_ITEM_RE.match(line):
                items.append(line)
            elif items:
                items[-1] = f"{items[-1]}\n{line}"
        else:
            footer.append(line)

    chunks: list[str] = []
    header_text = "\n".join(header).strip()
    if header_text:
        chunks.append(header_text)

    for item in items:
        item = item.strip()
        if not item:
            continue
        if len(item) <= max_chars:
            chunks.append(item)
            continue
        chunks.extend(split_message(item, max_chars=max_chars))

    footer_text = "\n".join(footer).strip()
    if footer_text:
        if chunks and len(chunks[-1]) + 2 + len(footer_text) <= max_chars:
            chunks[-1] = f"{chunks[-1]}\n\n{footer_text}"
        else:
            chunks.append(footer_text)
    return chunks


def load_weixin_account(home: Path, account_id: str) -> dict[str, Any]:
    path = home / ".openclaw/openclaw-weixin/accounts" / f"{account_id}.json"
    return load_json(path)


def prefix_chunk_messages(messages: list[str]) -> list[str]:
    if len(messages) <= 1:
        return messages
    total = len(messages)
    prefixed: list[str] = []
    for index, message in enumerate(messages, start=1):
        header = f"[{index}/{total}]"
        if message.startswith(header):
            prefixed.append(message)
        else:
            prefixed.append(f"{header}\n{message}")
    return prefixed


def send_weixin_api_message(
    *,
    account: dict[str, Any],
    target: str,
    message: str,
    context_token: str | None,
) -> dict[str, Any]:
    base_url = str(account.get("baseUrl") or "https://ilinkai.weixin.qq.com").rstrip("/")
    api_token = str(account.get("token") or "")
    if not api_token:
        return {"ok": False, "error": "missing_weixin_api_token"}

    client_id = f"openclaw-weixin:{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    body = {
        "msg": {
            "from_user_id": "",
            "to_user_id": target,
            "client_id": client_id,
            "message_type": 1,
            "message_state": 2,
            "item_list": [{"type": 1, "text_item": {"text": message}}],
            "context_token": context_token or None,
        }
    }
    request = Request(
        f"{base_url}/ilink/bot/sendmessage",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_token}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": "weixin_api_request_failed", "detail": str(exc)}

    errcode = payload.get("errcode", 0)
    if errcode not in (0, None):
        error = "weixin_session_timeout" if errcode == -14 else "weixin_api_error"
        return {
            "ok": False,
            "error": error,
            "api_response": payload,
            "message_id": client_id,
        }
    return {"ok": True, "message_id": client_id, "api_response": payload, "transport": "weixin_api"}


def read_gateway_delivery_issues(since_ts: float) -> list[str]:
    path = gateway_log_path()
    if not path:
        return []
    issues: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-400:]
    except OSError:
        return []
    for line in lines:
        if "contextToken missing" in line or "session timeout" in line:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                issues.append(line[-240:])
                continue
            ts_text = ((payload.get("_meta") or {}).get("date") or payload.get("time") or "")
            if ts_text:
                try:
                    ts = datetime.fromisoformat(str(ts_text).replace("Z", "+00:00")).timestamp()
                except ValueError:
                    ts = time.time()
            else:
                ts = time.time()
            if ts >= since_ts - 2:
                msg = payload.get("1") or payload.get("message") or line
                issues.append(str(msg))
    return issues


def send_openclaw_message(
    *,
    openclaw: str,
    account: str,
    target: str,
    message: str,
    context_token: str | None = None,
    account_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if account_config and context_token:
        api_result = send_weixin_api_message(
            account=account_config,
            target=target,
            message=message,
            context_token=context_token,
        )
        if api_result.get("ok"):
            return api_result
        if api_result.get("error") == "weixin_session_timeout":
            # Stale token on disk; fall through to gateway send for log evidence.
            pass
        elif api_result.get("error") in {"weixin_api_error", "missing_weixin_api_token"}:
            return api_result

    cmd = [
        openclaw,
        "message",
        "send",
        "--channel",
        "openclaw-weixin",
        "--account",
        account,
        "-t",
        target,
        "-m",
        message,
        "--json",
    ]
    if context_token:
        cmd.extend(["--delivery", json.dumps({"contextToken": context_token})])
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    result: dict[str, Any] = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
    }
    if proc.returncode == 0:
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result["error"] = "invalid_send_response"
            result["ok"] = False
            return result
        message_id = payload.get("messageId") or (payload.get("payload") or {}).get("result", {}).get("messageId")
        result["message_id"] = message_id
        if not message_id:
            result["error"] = "missing_message_id"
            result["ok"] = False
    else:
        result["error"] = "weixin_send_failed"

    issues = read_gateway_delivery_issues(started)
    if issues:
        result["delivery_warnings"] = issues
        if any("session timeout" in issue.lower() for issue in issues):
            result["error"] = "weixin_session_timeout"
            result["ok"] = False
        elif any("contextToken missing" in issue for issue in issues):
            result["error"] = "weixin_context_token_missing"
            result["ok"] = False
    return result


def send_messages(
    *,
    openclaw: str,
    account: str,
    target: str,
    messages: list[str],
    context_token: str | None = None,
    account_config: dict[str, Any] | None = None,
    pause_sec: float = 0.8,
    prefix_chunks: bool = True,
) -> dict[str, Any]:
    if prefix_chunks:
        messages = prefix_chunk_messages(messages)
    sent: list[dict[str, Any]] = []
    for index, message in enumerate(messages, start=1):
        outcome = send_openclaw_message(
            openclaw=openclaw,
            account=account,
            target=target,
            message=message,
            context_token=context_token,
            account_config=account_config,
        )
        outcome["chunk_index"] = index
        outcome["chunk_count"] = len(messages)
        outcome["chars"] = len(message)
        sent.append(outcome)
        if not outcome.get("ok"):
            return {
                "ok": False,
                "chunks": sent,
                "error": outcome.get("error", "chunk_send_failed"),
            }
        if index < len(messages):
            time.sleep(pause_sec)
    return {"ok": True, "chunks": sent, "chunk_count": len(messages)}
