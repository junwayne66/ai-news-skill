---
name: ai-news
description: Use when orchestrating a scheduled AI industry news workflow (daily or weekly) on OpenClaw or Hermes that discovers, verifies, summarizes, archives to Feishu Base, builds Feishu cards with source links, and publishes directly to Feishu group chats through deterministic scripts and atomic subagents.
---

# AI News Skill

Use this skill to run or implement an AI industry news workflow on OpenClaw or Hermes. The workflow is led by a main task agent that coordinates deterministic scripts and atomic specialist subagents, archives items to Feishu Base, builds a Feishu card from archived Base data with clickable source links, and publishes the card directly to the target group after internal quality review.

## Core Rule

After internal quality review passes, archive items to Feishu Base, read them back, build the Feishu card from archived fields, and publish directly to the target group. **Do not require administrator approval.** Do not publish from an unarchived draft.

## Coverage Requirements

Every run must actively cover these topic areas (see [references/news-sources.md](references/news-sources.md)):

- Model releases, funding, policy, research, infrastructure, community signals
- **Embodied intelligence** (具身智能)
- **Robotics** (机器人)
- **World models** (世界模型)

For `AI_NEWS_MODE=weekly`, rank by cross-week heat, impact, and evidence quality; prefer the hottest items rather than only the newest.

## Execution Principle

Use scripts for deterministic work and agents for uncertain judgment.

- Main agent: assemble inputs, call scripts, inspect script outputs, decide the next state, and assign subagents.
- Scripts: normalize run context, validate schemas, compute hashes, format Feishu payloads, call Feishu APIs, and write Feishu Base records.
- Subagents: find candidate news, judge credibility, rank impact, explain significance, edit the Chinese report, and review unsupported claims.
- Use `scripts/query_memory.py` for on-demand memory; do not preload all references into every role.

## Runtime Inputs

Require these inputs from platform config, secret manager, or task payload:

- `AI_NEWS_PLATFORM`: `openclaw` or `hermes`.
- `AI_NEWS_MODE`: `daily` (default) or `weekly`.
- `AI_NEWS_TIMEZONE`: default `Asia/Shanghai`.
- `AI_NEWS_WINDOW`: default `24h` for daily, `7d` for weekly.
- `AI_NEWS_MAX_ITEMS`: default `8`.
- `AI_NEWS_LANGUAGE`: default `zh-CN`.
- `FEISHU_GROUP_CHAT_ID`: target group chat for publishing.
- `FEISHU_BASE_APP_TOKEN`: target Feishu Base app token.
- `FEISHU_BASE_TABLE_ID`: target Feishu Base table ID.
- `FEISHU_NEWS_ADMIN_ID`: optional; not required when approval is disabled.
- Feishu app credentials configured for `lark-cli` message, card, and Base write permissions.
- [Agent Reach](https://github.com/Panniantong/agent-reach) installed and healthy. See [references/agent-reach-integration.md](references/agent-reach-integration.md).
- Shell/exec access enabled on the host.

If any required destination ID is missing, stop before collection and report the missing fields.

## Schedule

| Job | Cron (Asia/Shanghai) | Mode | Window |
| --- | --- | --- | --- |
| Weekday daily news | `0 8 * * 1-5` | `daily` | previous 24h |
| Sunday weekly digest | `0 20 * * 0` | `weekly` | previous 7d |

See [references/openclaw-runtime.md](references/openclaw-runtime.md) and [AGENT_DEPLOYMENT_GUIDE.md](AGENT_DEPLOYMENT_GUIDE.md) for cron setup.

## Main Agent Workflow

0. Sync Agent Reach health with `scripts/sync_agent_reach_health.py`, then build routing with `scripts/check_news_sources.py --refresh-reach`. If Agent Reach is unavailable, continue only in `rss_only` mode.
1. Normalize run context with `scripts/normalize_run_context.py`.
2. Query role-specific memory with `scripts/query_memory.py` before assigning each subagent.
3. Start the subagent loop from [references/subagent-contracts.md](references/subagent-contracts.md).
4. Collect candidates across all required topics, including embodied intelligence, robotics, and world models.
5. Verify source credibility, publication time, factual claims, and duplicate clusters.
6. Rank items by impact, novelty, evidence quality, and relevance. For weekly mode, prioritize week-level heat.
7. Draft the Feishu-ready Chinese report. Every item must include `primary_source_url`.
8. Run `scripts/validate_news_payload.py`.
9. Run the reviewer subagent and main-agent audit against [references/architecture.md](references/architecture.md).
10. Compute publish payload hash with `scripts/hash_payload.py`.
11. Ask `archive_record_builder` to prepare Base records. Write with `scripts/archive_feishu_base.py`.
12. Read back archived records with `scripts/fetch_feishu_base_records.py`.
13. Build the Feishu card with `scripts/build_feishu_card.py`. Each item must render a clickable `[原文链接](url)` from the archived `来源` field.
14. Publish the card to `FEISHU_GROUP_CHAT_ID` with `scripts/send_feishu_card.py`.
15. If internal review fails, rerun only the necessary subagent steps. Default max retry count is 3.

## Output Expectations

- Date window and timezone.
- 5-8 high-signal AI industry news items.
- One-line headline per item.
- Concise Chinese summary with business or technical significance.
- **Clickable original article link per item** in the Feishu card.
- Source links, publication dates, and confidence level in the payload and Base archive.
- Feishu card content generated from archived Base fields only.

## Reference Files

- [AGENT_DEPLOYMENT_GUIDE.md](AGENT_DEPLOYMENT_GUIDE.md): zero-base deployment for OpenClaw and Hermes via AI agents.
- [OPENCLAW_AGENT_RUNBOOK.md](OPENCLAW_AGENT_RUNBOOK.md): OpenClaw install and operate runbook.
- [references/architecture.md](references/architecture.md): architecture, state machine, quality gates.
- [references/agent-reach-integration.md](references/agent-reach-integration.md): Agent Reach integration.
- [references/news-sources.md](references/news-sources.md): topic policy and routing.
- [references/subagent-contracts.md](references/subagent-contracts.md): subagent roles and schemas.
- [references/openclaw-runtime.md](references/openclaw-runtime.md): cron, retries, runtime conventions.
- [references/feishu-workflow.md](references/feishu-workflow.md): Feishu archive, card, and publish flow.
- [references/openclaw-lark-cli-quickstart.md](references/openclaw-lark-cli-quickstart.md): lark-cli quickstart.
- [references/memory-index.md](references/memory-index.md): memory query hints.
