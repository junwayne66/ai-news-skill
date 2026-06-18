#!/usr/bin/env python3
"""Verify (and optionally live-test) WeChat notification delivery for ai-news."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from wechat_message import load_weixin_account, prepare_outbound_messages, send_messages, split_message


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_account(home: Path) -> str | None:
    env_account = os.getenv("WEIXIN_NOTIFY_ACCOUNT", "").strip()
    if env_account:
        return env_account

    sessions_path = home / ".openclaw/agents/main/sessions/sessions.json"
    if sessions_path.exists():
        sessions = json.loads(sessions_path.read_text(encoding="utf-8"))
        for value in sessions.values():
            origin = value.get("origin") or {}
            if origin.get("provider") == "openclaw-weixin" and origin.get("accountId"):
                return str(origin["accountId"])

    accounts_path = home / ".openclaw/openclaw-weixin/accounts.json"
    if accounts_path.exists():
        accounts = json.loads(accounts_path.read_text(encoding="utf-8"))
        for account_id in accounts:
            if account_id and account_id != "default":
                return str(account_id)
    return None


def resolve_target(home: Path, account: str) -> str | None:
    env_target = os.getenv("WEIXIN_NOTIFY_TARGET", "").strip()
    if env_target:
        return env_target

    token_path = home / ".openclaw/openclaw-weixin/accounts" / f"{account}.context-tokens.json"
    tokens = load_json(token_path)
    if tokens:
        for user_id, token in tokens.items():
            if isinstance(token, str) and token.strip():
                return user_id

    sessions_path = home / ".openclaw/agents/main/sessions/sessions.json"
    if sessions_path.exists():
        sessions = json.loads(sessions_path.read_text(encoding="utf-8"))
        for key, value in sessions.items():
            if "openclaw-weixin" not in key:
                continue
            route = value.get("route") or {}
            target = (route.get("target") or {}).get("to") or value.get("lastTo")
            if target and value.get("chatType", "direct") == "direct":
                return str(target)
    return None


def resolve_context_token(home: Path, account: str, target: str) -> str | None:
    token_path = home / ".openclaw/openclaw-weixin/accounts" / f"{account}.context-tokens.json"
    tokens = load_json(token_path)
    token = tokens.get(target)
    if isinstance(token, str) and token.strip():
        return token
    return None


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


def channel_configured(openclaw: str) -> bool:
    proc = subprocess.run(
        [openclaw, "channels", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return "openclaw-weixin" in output and "configured" in output and "enabled" in output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Send a live verification message")
    parser.add_argument("--message", default="[ai-news] 微信通知链路验证")
    parser.add_argument("--file", help="Send file contents (chunked) instead of --message")
    parser.add_argument("--max-chars", type=int, default=int(os.getenv("WEIXIN_CHUNK_MAX_CHARS", "1500")))
    args = parser.parse_args()

    home = Path.home()
    openclaw = openclaw_bin()

    result: dict[str, Any] = {
        "ok": False,
        "channel": "openclaw-weixin",
        "checks": {},
    }

    if not channel_configured(openclaw):
        result["error"] = "weixin_channel_not_configured"
        print(json.dumps(result, ensure_ascii=False))
        return 2

    result["checks"]["channel_configured"] = True

    account = resolve_account(home)
    if not account:
        result["error"] = "missing_weixin_account"
        print(json.dumps(result, ensure_ascii=False))
        return 2
    result["account"] = account
    result["checks"]["account_resolved"] = True

    target = resolve_target(home, account)
    if not target:
        result["error"] = "missing_weixin_target"
        result["hint"] = "set WEIXIN_NOTIFY_TARGET or send one inbound WeChat message to refresh context"
        print(json.dumps(result, ensure_ascii=False))
        return 2
    result["target"] = target
    result["checks"]["target_resolved"] = True

    context_token = resolve_context_token(home, account, target)
    if not context_token:
        result["error"] = "missing_context_token"
        result["hint"] = "send one inbound WeChat message to the bot to refresh contextToken"
        print(json.dumps(result, ensure_ascii=False))
        return 2
    result["checks"]["context_token_present"] = True
    account_config = load_weixin_account(home, account)

    if not args.live:
        result["ok"] = True
        result["mode"] = "verify-only"
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.file:
        message_text = Path(args.file).read_text(encoding="utf-8")
    else:
        message_text = args.message

    chunks = split_message(message_text, max_chars=args.max_chars) if args.file else prepare_outbound_messages(message_text, max_chars=args.max_chars)
    send_result = send_messages(
        openclaw=openclaw,
        account=account,
        target=target,
        messages=chunks,
        context_token=context_token,
        account_config=account_config,
    )
    result.update(send_result)
    if not send_result.get("ok"):
        result["hint"] = (
            "WeChat proactive delivery needs a fresh session. "
            "Send any message to the bot in WeChat, then retry within a few minutes."
        )
        print(json.dumps(result, ensure_ascii=False))
        return 2

    last_chunk = send_result["chunks"][-1]
    result["ok"] = True
    result["mode"] = "live"
    result["chunk_count"] = len(chunks)
    result["message_id"] = last_chunk.get("message_id")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
