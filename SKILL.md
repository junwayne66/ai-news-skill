---
name: ai-news
description: Use when orchestrating an OpenClaw scheduled daily AI industry news workflow that discovers, verifies, summarizes, reviews, requests Feishu approval, archives approved records to Feishu Base, builds Feishu cards from archived Base data, and publishes cards to Feishu group chats through deterministic scripts and atomic subagents.
---

# AI News Daily Skill

Use this skill to run or implement a daily AI industry news workflow on OpenClaw. The workflow is led by a main task agent that coordinates deterministic scripts and atomic specialist subagents, audits their outputs, requests approval from a designated Feishu news administrator, archives approved items to Feishu Base, builds a Feishu card from archived Base data, and publishes the card only after archive success.

## Core Rule

Never send AI news to the target Feishu group before the news administrator approves the exact payload and the approved items have been archived to Feishu Base. If the administrator rejects it, treat the feedback as a new instruction, rerun the relevant subagents, and repeat review and approval.

## Execution Principle

Use scripts for deterministic work and agents for uncertain judgment. Do not rely only on LLM reasoning for operations that can be computed, validated, hashed, parsed, rendered, or submitted through an API.

- Main agent: assemble inputs, call scripts, inspect script outputs, decide the next state, and assign subagents.
- Scripts: normalize OpenClaw input, validate schemas, compute hashes and idempotency keys, enforce mechanically checkable quality gates, format Feishu payloads, call Feishu APIs, and write Feishu Base records.
- Subagents: handle atomic uncertain tasks such as finding candidate news, judging source credibility, ranking industry impact, explaining significance, editing the Chinese report, and reviewing unsupported claims.
- Keep subagent context small. Pass only the task envelope, relevant items, evidence URLs, and required output schema.
- Agent and subagent memory must be loaded on demand with `scripts/query_memory.py`; do not preload all references into every role.
- If a deterministic script and an agent disagree, the main agent must stop and resolve the conflict before approval or publishing.

## Runtime Inputs

Require these inputs from platform config, secret manager, or task payload:

- `AI_NEWS_PLATFORM`: must be `openclaw`; default to `openclaw` when omitted by the OpenClaw runtime.
- `AI_NEWS_TIMEZONE`: default `Asia/Shanghai`.
- `AI_NEWS_WINDOW`: default previous 24 hours.
- `AI_NEWS_MAX_ITEMS`: default 8.
- `AI_NEWS_LANGUAGE`: default `zh-CN`.
- `FEISHU_NEWS_ADMIN_ID`: Feishu user ID or open ID for approval.
- `FEISHU_GROUP_CHAT_ID`: target group chat for publishing.
- `FEISHU_BASE_APP_TOKEN`: target Feishu Base app token.
- `FEISHU_BASE_TABLE_ID`: target Feishu Base table ID.
- Feishu app credentials configured for `lark-cli` message, card callback, and Base write permissions.
- Source access configuration, such as search APIs, RSS lists, official newsroom URLs, or approved OpenClaw web tools.

If any required secret or destination ID is missing, stop before collection and report the missing fields.

## Main Agent Workflow

1. Normalize the OpenClaw scheduled run context into a single `RunContext` with `scripts/normalize_run_context.py`.
2. Load [references/openclaw-runtime.md](references/openclaw-runtime.md) only when wiring OpenClaw cron, secrets, retries, or run state.
3. Query role-specific memory with `scripts/query_memory.py` before assigning each subagent.
4. Start the subagent collaboration loop from [references/subagent-contracts.md](references/subagent-contracts.md). Use atomic subagents whenever possible. If real subagent tools are unavailable, emulate the roles as separate labeled passes and preserve the same contracts.
5. Collect candidate AI industry news from approved source channels.
6. Verify source credibility, publication time, factual claims, and duplicate clusters.
7. Rank items by impact, novelty, evidence quality, and relevance to the target audience.
8. Draft the Feishu-ready Chinese daily report with source links and confidence markers.
9. Run deterministic validation with `scripts/validate_news_payload.py`.
10. Run the reviewer subagent. The main agent must also audit the result against the quality gates in [references/architecture.md](references/architecture.md).
11. Freeze the approval payload and compute its hash with `scripts/hash_payload.py`.
12. Send the approval request to the Feishu news administrator with `scripts/send_feishu_message.py` or a future approval-card script described in [references/feishu-workflow.md](references/feishu-workflow.md).
13. If approved, ask the archive subagent to prepare archive records, then write them to Feishu Base with `scripts/archive_feishu_base.py`.
14. Read the archived records back from Feishu Base with `scripts/fetch_feishu_base_records.py`.
15. Build the final Feishu card from fetched Base record fields with `scripts/build_feishu_card.py`.
16. Publish the card to the configured Feishu group with `scripts/send_feishu_card.py`.
17. If rejected, capture the administrator's feedback, reopen the task board, rerun the smallest necessary subagent steps, and repeat steps 9-16. Default maximum retry count is 3 unless OpenClaw policy says otherwise.

## Context And Memory

Keep the active context short:

- Load `SKILL.md` for the top-level workflow.
- Use `scripts/query_memory.py --query "<topic>"` to retrieve only the reference snippets needed by the current role.
- Pass each subagent only its task envelope, item slice, evidence URLs, output schema, and directly relevant feedback.
- Store durable run history outside prompt context, preferably OpenClaw run state and Feishu Base records.

## Output Expectations

The final published report should include:

- Date window and timezone.
- 5-8 high-signal AI industry news items.
- One-line headline for each item.
- Concise Chinese summary with business or technical significance.
- Source links, publication dates, and confidence level.
- Feishu card content generated from archived Feishu Base fields, not from an unarchived draft.
- Optional sections for "值得关注" and "待确认", but only if evidence supports them.

Avoid unsupported rumors, vague trend filler, duplicate items, and exaggerated claims.

## Reference Files

- [references/architecture.md](references/architecture.md): end-to-end architecture, state machine, quality gates, retry behavior, and observability.
- [references/subagent-contracts.md](references/subagent-contracts.md): subagent roles, message envelopes, review contracts, and handoff schemas.
- [references/openclaw-runtime.md](references/openclaw-runtime.md): OpenClaw cron, run state, retries, installation, and runtime conventions.
- [references/feishu-workflow.md](references/feishu-workflow.md): approval card, group publishing, callback handling, and Feishu Base archive schema.
- [references/script-boundaries.md](references/script-boundaries.md): what must be implemented as deterministic scripts and what remains agent-driven.
- [references/openclaw-lark-cli-quickstart.md](references/openclaw-lark-cli-quickstart.md): install and run this skill quickly on OpenClaw with the official `lark-cli`.
- [references/memory-index.md](references/memory-index.md): query hints for loading only the reference snippets each agent needs.
