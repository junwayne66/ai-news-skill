# Memory Index

Use `scripts/query_memory.py` to load only the snippets needed for the current task.

## Suggested Queries

| Need | Query |
| --- | --- |
| OpenClaw installation and cron | `openclaw install cron skill` |
| Runtime context and retry | `openclaw run_context retry idempotency` |
| Deterministic versus agent boundary | `script deterministic agent boundary` |
| Subagent role contracts | `subagent role envelope peer_request` |
| Feishu direct publish | `feishu group publish source link card` |
| Feishu Base archive | `feishu base archive records fields url` |
| Weekly digest mode | `weekly mode hottest items 7d` |
| Embodied robotics topics | `embodied intelligence robotics world model` |
| Agent deployment | `agent deployment guide openclaw hermes` |
| Quality gates | `quality gates source duplicate confidence` |
| Agent Reach integration | `agent reach integration doctor json` |
| News channel policy | `news channel policy routing fallback` |
| Source health scripts | `sync agent reach health check news sources` |

## Loading Rule

Agents should request no more than 3-5 snippets per step. If a snippet reveals that another reference is needed, issue a second targeted query instead of loading every reference.
