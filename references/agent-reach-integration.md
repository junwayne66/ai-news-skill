# Agent Reach Integration

AI News treats [Agent Reach](https://github.com/Panniantong/agent-reach) as the **internet capability layer**. Agent Reach selects, installs, probes, and routes platform channels. AI News only decides which channels matter for AI industry news, which domains and RSS feeds are trusted, and how to degrade when channels fail.

## Responsibility Split

| Layer | Owns | Does not own |
| --- | --- | --- |
| Agent Reach | Channel health, backend routing, upstream CLI install/update | News topic policy, Feishu workflow, report quality |
| AI News | Topic-to-channel policy, RSS/domain allowlists, routing, Loop orchestration | Whether `twitter` uses `twitter-cli` or `opencli` |

## Prerequisites

1. OpenClaw exec access:
   ```bash
   openclaw config set tools.profile "coding"
   ```
2. Install Agent Reach using the official guide:
   - Install: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
   - Update: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
3. Co-install the Agent Reach skill when possible:
   ```bash
   openclaw skills install ~/.openclaw/skills/agent-reach --as agent-reach --force
   ```

## Machine-Readable Contract

AI News scripts only consume these Agent Reach commands:

| Command | Purpose | Consumer |
| --- | --- | --- |
| `agent-reach doctor --json` | Channel health and `active_backend` | `scripts/sync_agent_reach_health.py` |
| `agent-reach watch` | Daily health and update scan | OpenClaw cron |
| `agent-reach check-update` | Version check | Upgrade decision |
| `agent-reach version` | Installed version | Compatibility gate |

Do not parse human-readable `agent-reach doctor` text output in AI News scripts.

## Upgrade Adaptation Rules

1. AI News config references **channel names only** (`web`, `rss`, `github`, `exa_search`, `twitter`, ...).
2. Never hardcode backend names such as `twitter-cli`, `opencli`, or `bili-cli`.
3. Backend changes are observed through `doctor --json` → `active_backend`.
4. When Agent Reach adds a new channel, update [`config/news_channel_policy.yaml`](../config/news_channel_policy.yaml) only.
5. If `doctor --json` changes shape in a breaking way, update only [`scripts/sync_agent_reach_health.py`](../scripts/sync_agent_reach_health.py).

Compatibility settings live in [`config/agent_reach_compat.yaml`](../config/agent_reach_compat.yaml).

## AI News Entry Steps

Before collection, the main agent must run:

```bash
scripts/sync_agent_reach_health.py
scripts/check_news_sources.py --refresh-reach
```

Expected flow:

1. `sync_agent_reach_health.py` writes `/tmp/ai-news-reach-health.json` (or `AI_NEWS_HEALTH_SNAPSHOT_PATH`).
2. `check_news_sources.py` merges Agent Reach channel health with RSS/domain probes.
3. The resulting `routing.allowed_channels` is injected into `source_collector`.

If Agent Reach is unavailable, AI News enters `rss_only` mode and should notify the administrator. Do not invent web search results without a healthy channel.

## Subagent Calling Rule

`source_collector` must call upstream tools directly, following the Agent Reach skill examples:

| Need | Channel | Example upstream call |
| --- | --- | --- |
| Read a page | `web` | `curl -s "https://r.jina.ai/URL"` |
| Semantic search | `exa_search` | `mcporter call 'exa.web_search_exa(...)'` |
| GitHub activity | `github` | `gh search repos/commits/releases ...` |
| RSS allowlist | `rss` | `feedparser` against policy feeds |
| Twitter signal | `twitter` | `twitter search "..."` when channel healthy |
| Bilibili signal | `bilibili` | `bili search "..."` when channel healthy |

AI News does not wrap these commands in custom CLIs.

## Recommended Cron Layout

| Time | Task |
| --- | --- |
| 08:00 | `agent-reach watch` |
| 08:30 | `scripts/sync_agent_reach_health.py && scripts/check_news_sources.py --refresh-reach` |
| 09:00 | Full AI News daily workflow |

## Failure Levels

| Level | Trigger | Action |
| --- | --- | --- |
| L1 | One RSS/domain source down | Skip source, use same-topic alternatives |
| L2 | One Agent Reach channel down | Route to fallback channel from policy |
| L3 | Agent Reach unavailable | `rss_only` mode + admin notification |

## Related Files

- [`news-sources.md`](news-sources.md)
- [`architecture.md`](architecture.md)
- [`subagent-contracts.md`](subagent-contracts.md)
- [`../config/news_channel_policy.yaml`](../config/news_channel_policy.yaml)
