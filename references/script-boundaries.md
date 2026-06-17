# Script Boundaries

Use this reference whenever deciding whether a step belongs in code or in an agent.

## Principle

Deterministic events use scripts. Uncertain events use agent judgment. The main agent assembles inputs, calls scripts, checks structured outputs, and then decides the next state.

This reduces hallucination risk and keeps subagent context short.

## Must Be Scripts

Implement these as scripts or platform command invocations:

- Normalize platform task payloads into `RunContext` (OpenClaw, Hermes, Claude, Cursor, Codex).
- Initialize, read, merge, and check completion of `loop_state.json`.
- Validate required environment variables and destination IDs.
- Validate JSON schemas for `RunContext`, `NewsItem`, approval payloads, and archive records.
- Compute item IDs, payload hashes, and idempotency keys.
- Check date-window inclusion when `published_at` is available.
- Verify URL syntax and canonicalize URLs.
- Build fixed Feishu card/message JSON from approved templates.
- Send Feishu approval requests, group messages, and Base writes through `lark-cli`.
- Validate Feishu callback signature, operator ID, expiry, and payload hash.
- Retry API calls with bounded backoff and structured error reporting.

## Agent Decisions

Use agents or subagents for:

- Searching for candidate news from broad or changing sources.
- Judging source credibility when sources conflict.
- Deciding whether a secondary source is sufficient.
- Ranking impact, novelty, and audience relevance.
- Explaining industry significance.
- Rewriting summaries after reviewer or administrator feedback.
- Choosing which pipeline step to rerun after a rejection.

## Main Agent Call Pattern

The main agent should use this loop:

```text
prepare minimal input
-> call deterministic script if available
-> pass clean slice to one atomic subagent
-> validate subagent output with script
-> decide next step
```

Do not pass the full run history to every subagent. Pass only:

- Run context identifiers and time window.
- The specific items the role must process.
- Relevant evidence URLs and notes.
- Required JSON output schema.
- Reviewer or administrator feedback, when directly relevant.

## Included Utility Scripts

These utility scripts provide deterministic building blocks:

- `scripts/normalize_run_context.py`: normalize platform payload and environment into a `RunContext`.
- `scripts/loop_state.py`: durable loop state init/read/write/check-done.
- `scripts/hash_payload.py`: canonicalize JSON or text and compute SHA-256 payload hashes.
- `scripts/validate_news_payload.py`: validate a draft report JSON before approval.
- `scripts/send_feishu_message.py`: send Feishu text messages through `lark-cli api`.
- `scripts/archive_feishu_base.py`: write Feishu Base records through `lark-cli api`.
- `scripts/fetch_feishu_base_records.py`: read archived Feishu Base records through `lark-cli api`.
- `scripts/build_feishu_card.py`: build Feishu interactive card JSON from fetched Base record fields.
- `scripts/send_feishu_card.py`: send Feishu interactive cards through `lark-cli api`.
- `scripts/query_memory.py`: return small relevant snippets from `SKILL.md` and `references/`.

Approval-card integrations are implemented with:

- `scripts/send_feishu_approval.py`
- `scripts/validate_feishu_callback.py`

Keep those scripts thin and boring: input JSON in, structured JSON out, non-zero exit on terminal failure.
