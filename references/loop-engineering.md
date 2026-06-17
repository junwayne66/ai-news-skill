# Loop Engineering

This skill is designed as a **loop**, not a one-shot prompt. The goal is to define purpose, verification, durable state, and stop rules so OpenClaw, Hermes, Claude Code, Codex, or Cursor can rerun until the daily briefing is approved, archived, and published — or stop safely with a clear escalation.

## Six Loop Components

| Component | In this skill | Implementation |
| --- | --- | --- |
| Scheduling | Daily trigger | OpenClaw cron, Claude `/loop`, GitHub Actions, Hermes scheduled task |
| Durable state | Cross-run memory | `data/runs/<job_id>/loop_state.json` via `scripts/loop_state.py` |
| Isolation | Clean daily context | OpenClaw `--session isolated`; fresh subagent envelopes per stage |
| Skills | Workflow knowledge | This `SKILL.md` plus `references/` loaded on demand |
| Connectors | External systems | `lark-cli`, Feishu Base, web/search tools, optional MCP |
| Sub-agents | Maker-checker split | Collector/verifier/ranker/editor vs `quality_reviewer` + admin approval |

## Loop Cycle

```text
observe state
→ plan smallest next step
→ act (script or subagent)
→ verify (script gate or reviewer)
→ persist state
→ repeat until done or stop rule fires
```

### Observe

Read `loop_state.json` before every stage transition:

```bash
scripts/loop_state.py read --job-id "$JOB_ID"
```

### Plan

The main agent chooses the smallest rerun slice after rejection or failure. Use `replan_advisor` only for uncertain replanning; use deterministic rules for known failures.

### Act

```text
script when deterministic
subagent when judgment required
never mix both in the same role call
```

### Verify

Every stage has a checkable exit:

| Stage | Verification |
| --- | --- |
| `fetching` | candidate count > 0 or explicit no-news completion |
| `url_deduping` | stable IDs, no duplicate primary URLs |
| `scoring` | every shortlisted item has scores |
| `filtering` | `validate_news_payload.py` returns `ok: true` |
| `drafting` | draft matches schema |
| `internal_review` | `quality_reviewer.status == pass` |
| `approval_pending` | admin message matches `payload_hash` |
| `archiving` | Base write returns record IDs |
| `publishing` | group message ID returned |

Prefer deterministic verification. Use LLM review only where mechanical checks cannot decide.

### Persist

After every verified transition:

```bash
echo '{"stage":"filtering","candidate_count":24}' | scripts/loop_state.py write --job-id "$JOB_ID" --merge
```

## Termination Conditions

### Success

All must be true:

- `loop_state.stage == completed`
- `payload_hash` approved by administrator
- Feishu Base archive succeeded
- Feishu card built from archived read-back
- Group publish returned `message_id`

### Safe stop

Stop without publish when:

- required secrets or destination IDs are missing
- `iteration_count >= max_iterations` (default 3 per rejection cycle)
- same blocking error repeats twice with no state change
- `quality_reviewer` fails after max editor retries
- administrator rejects and `replan_advisor` returns `blocked`

### Escalation

Notify the Feishu news administrator when:

- archive fails after 3 retries
- approval callback hash mismatch
- publish succeeds but read-back does not match archived records
- platform connector unavailable for entire run

## Maker-Checker Pattern

Horizon scores and summarizes in one pipeline. Loop engineering separates creation from verification:

| Maker | Checker |
| --- | --- |
| `source_collector` | `source_verifier` |
| `dedupe_ranker` | `source_verifier` peer review |
| `report_editor` | `quality_reviewer` |
| main agent draft freeze | administrator approval |
| `archive_record_builder` | `scripts/archive_feishu_base.py` + read-back |

The actor must not be the only grader for the same gate. `quality_reviewer` and administrator approval are mandatory checkers before publish.

## Iteration And Cost Guards

Defaults in `RunContext` / `loop_state.json`:

```json
{
  "max_iterations": 3,
  "max_subagent_calls_per_stage": 2,
  "max_items": 8,
  "no_progress_threshold": 2
}
```

No-progress detection:

- same `blocking_issues` hash across consecutive reviewer failures
- same candidate set after collector rerun with identical rejection reasons
- identical `payload_hash` resubmitted without editor changes

When no-progress triggers, stop and escalate instead of burning tokens.

## Durable State Schema

`loop_state.json` is the source of truth outside the LLM context:

```json
{
  "job_id": "ai-news-2026-06-17-asia-shanghai",
  "platform": "openclaw",
  "executor": "openclaw",
  "stage": "filtering",
  "stage_history": ["scheduled", "fetching", "url_deduping", "scoring", "filtering"],
  "iteration_count": 0,
  "max_iterations": 3,
  "candidate_count": 24,
  "verified_count": 14,
  "shortlist_count": 8,
  "payload_hash": null,
  "approval_status": null,
  "archive_record_ids": [],
  "publish_message_id": null,
  "last_error": null,
  "blocking_issue_hash": null,
  "updated_at": "ISO-8601"
}
```

The model forgets between runs. The repo and `loop_state.json` do not.

## Rejection Loop

```text
approval_pending
  → rejected
  → replanning (replan_advisor)
  → smallest rerun (collecting|verifying|ranking|drafting)
  → internal_review
  → approval_pending
```

Increment `iteration_count` on each rejection. Do not restart from `fetching` unless the administrator asks for new sources.

## Platform-Neutral Loop Contract

Any supported platform must implement the same five hooks:

1. `normalize` → `RunContext`
2. `state_read` / `state_write`
3. `dispatch_subagent(role, envelope)`
4. `run_script(name, input)`
5. `await_human_approval(payload_hash)` or callback validation

See [platform-adapters.md](platform-adapters.md) for OpenClaw, Hermes, and Claude-specific bindings.
