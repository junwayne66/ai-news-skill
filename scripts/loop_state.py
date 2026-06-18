#!/usr/bin/env python3
"""Read and write durable loop state outside the LLM context window."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "data" / "runs"

VALID_STAGES = [
    "scheduled",
    "fetching",
    "url_deduping",
    "scoring",
    "topic_deduping",
    "balancing",
    "enriching",
    "drafting",
    "internal_review",
    "approval_pending",
    "approved",
    "archiving",
    "card_building",
    "publishing",
    "completed",
    "rejected",
    "replanning",
    "failed_retriable",
    "failed_terminal",
]


def state_path(job_id: str) -> Path:
    return RUNS_DIR / job_id / "loop_state.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_state(job_id: str, platform: str, executor: str | None = None) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": platform,
        "executor": executor or platform,
        "stage": "scheduled",
        "stage_history": ["scheduled"],
        "iteration_count": 0,
        "max_iterations": 3,
        "candidate_count": 0,
        "verified_count": 0,
        "shortlist_count": 0,
        "payload_hash": None,
        "approval_status": None,
        "archive_record_ids": [],
        "publish_message_id": None,
        "card_hash": None,
        "last_error": None,
        "blocking_issue_hash": None,
        "no_progress_streak": 0,
        "updated_at": now_iso(),
    }


def read_state(job_id: str) -> dict[str, Any]:
    path = state_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"loop state not found for job_id={job_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(job_id: str, state: dict[str, Any]) -> Path:
    path = state_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_iso()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def advance_stage(state: dict[str, Any], stage: str) -> None:
    if stage not in VALID_STAGES:
        raise ValueError(f"invalid stage: {stage}")
    state["stage"] = stage
    history = state.setdefault("stage_history", [])
    if not history or history[-1] != stage:
        history.append(stage)


def cmd_init(args: argparse.Namespace) -> int:
    path = state_path(args.job_id)
    if path.exists() and not args.force:
        print(json.dumps({"ok": False, "error": "state_exists", "path": str(path)}, ensure_ascii=False))
        return 2
    state = default_state(args.job_id, args.platform, args.executor)
    if args.max_iterations:
        state["max_iterations"] = args.max_iterations
    saved = write_state(args.job_id, state)
    print(json.dumps({"ok": True, "path": str(saved), "state": state}, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    try:
        state = read_state(args.job_id)
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "state": state}, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    try:
        state = read_state(args.job_id)
    except FileNotFoundError:
        platform = args.platform or "openclaw"
        state = default_state(args.job_id, platform, args.executor)

    patch = json.loads(sys.stdin.read() or "{}")
    if not isinstance(patch, dict):
        print(json.dumps({"ok": False, "error": "stdin must be a JSON object"}))
        return 2

    if "stage" in patch:
        advance_stage(state, patch["stage"])
        patch = {k: v for k, v in patch.items() if k != "stage"}

    state.update(patch)
    saved = write_state(args.job_id, state)
    print(json.dumps({"ok": True, "path": str(saved), "state": state}, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_check_done(args: argparse.Namespace) -> int:
    try:
        state = read_state(args.job_id)
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "done": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    done = (
        state.get("stage") == "completed"
        and bool(state.get("publish_message_id"))
        and bool(state.get("payload_hash"))
        and bool(state.get("archive_record_ids"))
    )
    should_stop = done or state.get("stage") == "failed_terminal"
    over_iterations = state.get("iteration_count", 0) >= state.get("max_iterations", 3) and state.get("stage") == "rejected"

    print(
        json.dumps(
            {
                "ok": True,
                "done": done,
                "should_stop": should_stop or over_iterations,
                "stage": state.get("stage"),
                "iteration_count": state.get("iteration_count", 0),
                "max_iterations": state.get("max_iterations", 3),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if done else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage durable loop state for ai-news")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Create a new loop state file")
    init_parser.add_argument("--job-id", required=True)
    init_parser.add_argument("--platform", default="openclaw")
    init_parser.add_argument("--executor", default=None)
    init_parser.add_argument("--max-iterations", type=int, default=3)
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=cmd_init)

    read_parser = sub.add_parser("read", help="Read loop state")
    read_parser.add_argument("--job-id", required=True)
    read_parser.set_defaults(func=cmd_read)

    write_parser = sub.add_parser("write", help="Merge stdin JSON into loop state")
    write_parser.add_argument("--job-id", required=True)
    write_parser.add_argument("--platform", default=None)
    write_parser.add_argument("--executor", default=None)
    write_parser.set_defaults(func=cmd_write)

    check_parser = sub.add_parser("check-done", help="Exit 0 only when loop completed successfully")
    check_parser.add_argument("--job-id", required=True)
    check_parser.set_defaults(func=cmd_check_done)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
