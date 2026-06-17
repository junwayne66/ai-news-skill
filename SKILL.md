---
name: ai-news
description: Use when orchestrating a Horizon-style daily AI industry news loop across OpenClaw, Hermes, Claude, Cursor, or Codex. The loop fetches and deduplicates sources, scores and enriches items, drafts and reviews a Chinese report, requests Feishu approval, archives approved records to Feishu Base, builds cards from archived data, and publishes only after deterministic verification and durable loop_state persistence.
---

# AI News Daily Skill

Run a **loop-engineered**, **Horizon-inspired** daily AI industry news workflow. A main orchestrator agent coordinates deterministic scripts and atomic specialist subagents, persists durable state outside the context window, verifies every stage, and only publishes after human approval and Feishu Base archive success.

Inspired by [Horizon](https://github.com/Thysrael/Horizon) data flow and [loop engineering](references/loop-engineering.md) stop rules.

## Core Rule

Never send AI news to the target Feishu group before:

1. the news administrator approves the exact `payload_hash`,
2. approved items are archived to Feishu Base,
3. the Feishu card is built from archived Base read-back fields.

If the administrator rejects the draft, treat feedback as a new instruction, rerun the smallest necessary stages, and repeat review and approval.

## Loop Engineering Principle

Design the system that prompts the agent, not a one-shot prompt.

| Component | Implementation |
| --- | --- |
| Schedule | OpenClaw cron, Claude `/loop`, Codex automation, Cursor cloud task |
| Durable state | `data/runs/<job_id>/loop_state.json` via `scripts/loop_state.py` |
| Isolation | OpenClaw `--session isolated`; fresh subagent envelopes per stage |
| Skills | This file plus on-demand `scripts/query_memory.py` |
| Connectors | `lark-cli`, Feishu Base, web/search tools, optional MCP |
| Maker-checker | editor vs `quality_reviewer`; main agent vs administrator |

Every stage transition must:

```text
read loop_state → act → verify → write loop_state
```

Stop when `scripts/loop_state.py check-done --job-id <id>` exits 0, or when `max_iterations` / no-progress rules fire. See [references/loop-engineering.md](references/loop-engineering.md).

## Horizon Pipeline

Map Horizon stages onto this skill. See [references/horizon-pipeline.md](references/horizon-pipeline.md).

```text
config → fetch → url_dedupe → score → filter → topic_dedupe → balance → enrich → draft → review → approve → archive → publish
```

| Stage | Owner |
| --- | --- |
| `fetching` | `source_collector` |
| `url_deduping` | script or `dedupe_ranker` |
| `scoring`, `topic_deduping`, `balancing` | `dedupe_ranker` |
| `enriching` | `industry_analyst` |
| `drafting` | `report_editor` |
| `internal_review` | `quality_reviewer` + main agent |
| `approval_pending` → `archiving` → `publishing` | scripts + main agent |

## Execution Principle

Scripts for deterministic work. Agents for uncertain judgment.

- **Orchestrator** (OpenClaw / Claude / Cursor): assemble inputs, call scripts, inspect outputs, advance `loop_state`, dispatch subagents, request approval, authorize publish.
- **Executor** (optional Hermes): run bounded fetch/rank/enrich slices via ACP or JSON handoff; never publish directly.
- **Scripts**: normalize context, validate schemas, hash payloads, manage loop state, call Feishu APIs, archive and read-back Base records.
- **Subagents**: discover news, verify sources, rank clusters, explain significance, edit Chinese copy, review claims, prepare archive fields, advise replans.

If a script and a subagent disagree, stop and resolve before approval or publishing.

## Platform Support

Set `AI_NEWS_PLATFORM` to one of: `openclaw`, `hermes`, `claude`, `cursor`, `codex`.

| Platform | Typical role |
| --- | --- |
| `openclaw` | production orchestrator + cron |
| `hermes` | execution sub-loops with reflective skill accumulation |
| `claude` | developer `/loop` or `/goal` runs |
| `cursor` | cloud agent + repo workflow |
| `codex` | automations and background worktrees |

Recommended production topology: **OpenClaw orchestrates, Hermes executes repetitive slices, Claude/Cursor for local iteration**. See [references/platform-adapters.md](references/platform-adapters.md).

## Runtime Inputs

### Required for orchestrated delivery

- `AI_NEWS_PLATFORM`: default `openclaw`
- `AI_NEWS_EXECUTOR`: optional override; defaults to platform
- `AI_NEWS_TIMEZONE`: default `Asia/Shanghai`
- `AI_NEWS_WINDOW`: default `24h`
- `AI_NEWS_MAX_ITEMS`: default `8`
- `AI_NEWS_LANGUAGE`: default `zh-CN`
- `AI_NEWS_CONFIG`: default `data/config.json`
- `FEISHU_NEWS_ADMIN_ID`, `FEISHU_GROUP_CHAT_ID`, `FEISHU_BASE_APP_TOKEN`, `FEISHU_BASE_TABLE_ID`
- Feishu app credentials for `lark-cli`
- AI provider key per `data/config.json` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.)

Hermes executor-only slices may omit Feishu destination IDs until the orchestrator reaches delivery stages.

If required secrets or destination IDs are missing for the active platform, stop before collection and report missing fields.

## Main Agent Workflow

1. `scripts/normalize_run_context.py` → `RunContext`
2. `scripts/loop_state.py init --job-id <id> --platform <platform>`
3. Load config from `data/config.json` (copy from `data/config.example.json` if needed)
4. `scripts/query_memory.py` before each subagent dispatch
5. Advance the Horizon pipeline stages in [references/subagent-contracts.md](references/subagent-contracts.md)
6. After each verified stage, `scripts/loop_state.py write --job-id <id>` with updated counts and `stage`
7. `scripts/validate_news_payload.py` before review
8. `quality_reviewer` maker-checker pass; main agent audits [references/architecture.md](references/architecture.md) quality gates
9. `scripts/hash_payload.py` → freeze approval payload
10. `scripts/send_feishu_message.py` → administrator approval
11. On approval: `archive_record_builder` → `scripts/archive_feishu_base.py` → `scripts/fetch_feishu_base_records.py` → `scripts/build_feishu_card.py` → `scripts/send_feishu_card.py`
12. On rejection: `replan_advisor` → rerun smallest slice → increment `iteration_count`
13. Mark `loop_state.stage = completed` only after publish `message_id` exists

## Context And Memory

Keep active context short:

- Load `SKILL.md` for top-level workflow only.
- `scripts/query_memory.py --query "<topic>" --top-k 3`
- Pass each subagent only its envelope, item slice, evidence URLs, output schema, and direct feedback.
- Persist counts, hashes, IDs, and stage in `loop_state.json`, not in prompt history.

## Output Expectations

- Date window and timezone
- 5-8 high-signal AI industry news items after Horizon-style scoring and balancing
- One-line headline, concise Chinese summary, business/technical significance
- Source links, publication dates, confidence markers
- Optional `值得关注` / `待确认` sections when evidence supports them
- Feishu card generated from archived Base fields only

Avoid rumors, duplicate clusters, vague filler, and exaggerated claims.

## Reference Files

- [references/horizon-pipeline.md](references/horizon-pipeline.md): Horizon core data flow mapped to this skill
- [references/loop-engineering.md](references/loop-engineering.md): durable state, stop rules, maker-checker, iteration guards
- [references/platform-adapters.md](references/platform-adapters.md): OpenClaw, Hermes, Claude, Cursor, Codex bindings
- [references/architecture.md](references/architecture.md): end-to-end architecture, state machine, quality gates
- [references/subagent-contracts.md](references/subagent-contracts.md): roles, envelopes, Horizon stage mapping
- [references/openclaw-runtime.md](references/openclaw-runtime.md): OpenClaw cron, retries, installation
- [references/feishu-workflow.md](references/feishu-workflow.md): approval, publishing, Base schema
- [references/script-boundaries.md](references/script-boundaries.md): script vs agent boundaries
- [references/memory-index.md](references/memory-index.md): query hints per role
- [data/config.example.json](data/config.example.json): Horizon-style sources, filtering, loop limits
