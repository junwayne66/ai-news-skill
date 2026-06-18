# Memory Index

Use `scripts/query_memory.py` to load only the snippets needed for the current task.

## Suggested Queries

| Need | Query |
| --- | --- |
| Remote host SSH and paths | `remote host ssh spark openclaw share skills` |
| Remote deploy flow | `remote deploy rsync openclaw skills install` |
| E2E smoke test | `e2e smoke test fetch_sources url_dedupe` |
| Script-first fetch pipeline | `fetch_sources url_dedupe prefetched collector` |
| Deterministic source collectors | `fetch_rss fetch_hackernews fetch_sources` |
| Loop engineering stop rules | `loop state termination maker checker` |
| Platform adapters | `openclaw hermes claude platform adapter` |
| OpenClaw installation and cron | `openclaw install cron skill` |
| Runtime context and retry | `openclaw run_context retry idempotency` |
| Loop state persistence | `loop_state stage iteration` |
| Deterministic versus agent boundary | `script deterministic agent boundary` |
| Subagent role contracts | `subagent role envelope peer_request` |
| Feishu approval | `feishu approval payload_hash admin` |
| Feishu group publishing | `feishu group publish message_id` |
| Feishu Base archive | `feishu base archive records fields` |
| Quality gates | `quality gates source duplicate confidence` |
| Balanced digest / category limits | `category_groups max_items filtering` |

## Loading Rule

Agents should request no more than 3-5 snippets per step. If a snippet reveals that another reference is needed, issue a second targeted query instead of loading every reference.

## Role-Specific First Queries

| Role | Start with |
| --- | --- |
| `source_collector` | `prefetched_items discovery_policy official search gap fill` |
| `dedupe_ranker` | `horizon dedupe score threshold category` |
| `industry_analyst` | `horizon enrich significance` |
| `quality_reviewer` | `quality gates loop maker checker` |
| orchestrator on OpenClaw | `openclaw cron loop_state platform` |
| remote production host | `ssh spark remote-spark wayne share skills` |
| Hermes executor | `hermes executor envelope handoff` |
