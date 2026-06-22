# News Sources

AI News uses a **policy layer** on top of Agent Reach. Agent Reach answers "which internet channels are healthy and which backend is active". AI News answers "which channels and domains should be used for AI industry news today".

## Data Model

### NewsSource

A concrete allowlisted source entry:

```json
{
  "id": "openai-blog-rss",
  "domain": "openai.com",
  "feed_url": "https://openai.com/blog/rss.xml",
  "topics": ["model_release"],
  "region": "global",
  "priority": 1
}
```

### NewsChannelPolicy

Topic-level routing policy stored in [`config/news_channel_policy.yaml`](../config/news_channel_policy.yaml):

```yaml
topics:
  model_release:
    primary_channels: [web, github, exa_search, rss]
    preferred_domains: [openai.com, anthropic.com]
    rss_feeds:
      openai-blog-rss: https://openai.com/blog/rss.xml
```

Policy references **Agent Reach channel names only**, never backend implementations.

### ReachChannelHealth

Produced by `scripts/sync_agent_reach_health.py` from `agent-reach doctor --json`:

```json
{
  "web": {
    "status": "healthy",
    "active_backend": "Jina Reader",
    "message": "..."
  }
}
```

Status mapping:

| Agent Reach `status` | AI News `status` |
| --- | --- |
| `ok` | `healthy` |
| `warn` | `degraded` |
| `off`, `error` | `down` |

### SourceHealth

Merged view used by the main loop:

- channel health from Agent Reach
- RSS/domain probe results from `scripts/check_news_sources.py`

### SourceRouting

Runtime routing object injected into `source_collector`:

```json
{
  "mode": "normal",
  "allowed_channels": ["web", "rss", "github", "exa_search"],
  "degraded_channels": ["twitter"],
  "blocked_channels": ["reddit"],
  "coverage_alerts": [],
  "topic_routes": {},
  "healthy_primary_count": 3
}
```

## Topic Coverage

Current policy topics:

| Topic | Primary channels | Notes |
| --- | --- | --- |
| `model_release` | web, github, exa_search, rss | Official labs and model vendors |
| `funding` | exa_search, web, rss | Funding and M&A |
| `policy_regulation` | web, exa_search, rss | Government and regulator updates |
| `research` | web, github, exa_search, rss | Papers and research labs |
| `infra` | web, exa_search, rss | Chips, cloud, hardware |
| `community_signal` | twitter, reddit, bilibili, exa_search | Optional social signal |
| `embodied_intelligence` | web, exa_search, rss, github | Embodied AI, physical intelligence |
| `robotics` | web, exa_search, rss, github | Humanoid and industrial robotics |
| `world_model` | web, exa_search, rss, github | World models, video/3D foundation models |

`community_signal` is optional. Missing social channels must not block the daily report.

## Automatic Updates

### Active checks

- Daily `agent-reach watch` cron
- Daily `scripts/sync_agent_reach_health.py`
- Daily `scripts/check_news_sources.py --refresh-reach`

### Passive degradation during collection

- Channel fails twice in one run → mark degraded for that run
- Switch to `fallback_channels` from policy (`web`, `rss`, `exa_search`, `github`)
- If all channels in a topic fail → emit `coverage_alerts`

## Remediation Playbook

### Single RSS feed fails

1. `check_news_sources.py` marks feed `down`
2. Collector skips that feed
3. Collector uses other feeds or `exa_search` for the same topic

### Single Agent Reach channel fails

1. `doctor --json` marks channel `down` or `degraded`
2. `build_routing()` removes it from `allowed_channels`
3. `replan_advisor` may rerun only `source_collector` and `source_verifier`

### Agent Reach unavailable

1. `sync_agent_reach_health.py` returns `fallback: "rss_only"`
2. Main agent notifies administrator with install/update doc links
3. Collector uses RSS allowlist and direct `web` reads only if still healthy

## Configuration Evolution

Preferred order:

1. Update [`config/news_channel_policy.yaml`](../config/news_channel_policy.yaml) in git
2. Re-run health scripts
3. Dry-run collection before changing production cron

Optional later step: mirror policy rows into Feishu Base for admin editing. The script contract should remain the same.

## Related Files

- [`agent-reach-integration.md`](agent-reach-integration.md)
- [`architecture.md`](architecture.md)
- [`subagent-contracts.md`](subagent-contracts.md)
