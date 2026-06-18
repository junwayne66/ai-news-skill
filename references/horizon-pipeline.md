# Horizon Pipeline Reference

This skill borrows the core data flow from [Horizon](https://github.com/Thysrael/Horizon) and maps it onto an agent-orchestrated daily AI news workflow with human approval and Feishu delivery.

Horizon is a deterministic Python pipeline. This skill keeps Horizon's stage boundaries and data shapes, but routes uncertain stages to atomic subagents and keeps mechanically checkable stages in scripts.

## Horizon Core Loop

```text
config → fetch → url_dedupe → ai_score → threshold_filter → topic_dedupe → enrich → summarize → deliver
```

Horizon's `HorizonOrchestrator.run()` implements this as:

1. Determine time window from config or `--hours`.
2. Fetch all configured sources concurrently into unified `ContentItem` objects.
3. Merge cross-source duplicates by normalized URL.
4. AI-score every item (0-10) with provider-configurable models.
5. Filter by `ai_score_threshold`, sort descending.
6. Semantic topic deduplication on titles/tags/summaries.
7. Optional balanced digest with per-category quotas (`category_groups`, `max_items`).
8. Enrich important items with web background search and community discussion.
9. Generate bilingual Markdown summaries.
10. Deliver to GitHub Pages, email, webhook, or MCP.

## Mapping To This Skill

| Horizon stage | Skill stage | Owner | Output artifact |
| --- | --- | --- | --- |
| Config load | `normalize_run_context` + `data/config.json` | Script | `RunContext` |
| Fetch | `fetching` | `fetch_sources` + `url_dedupe` scripts, then `source_collector` gap fill | `CandidateItem[]` |
| URL dedupe | `url_deduping` | `url_dedupe.py` script | `ContentItem[]` with stable IDs |
| AI score | `scoring` | `dedupe_ranker` | items with `impact_score`, `novelty_score`, `evidence_score` |
| Threshold filter | `filtering` | Script `validate_news_payload.py` + main agent | shortlist within `max_items` |
| Topic dedupe | `topic_deduping` | `dedupe_ranker` | clustered items |
| Category balance | `balancing` | `dedupe_ranker` + config | balanced shortlist |
| Enrich | `enriching` | `industry_analyst` | significance notes, watch-next |
| Summarize | `drafting` | `report_editor` | Feishu-ready Chinese draft |
| Deliver | `approval_pending → archiving → publishing` | Scripts + main agent | Feishu card from archived Base |

## Unified Content Model

Borrow Horizon's `ContentItem` shape and extend it for this skill's approval workflow:

```json
{
  "id": "rss:feed-name:entry-id-or-stable-url-hash",
  "source_type": "rss|hackernews|reddit|telegram|twitter|github|official|search",
  "headline": "string",
  "url": "https://...",
  "content": "optional raw excerpt",
  "author": "optional",
  "published_at": "ISO-8601",
  "fetched_at": "ISO-8601",
  "metadata": {
    "feed_name": "string",
    "category": "model|product|funding|policy|research|infra|enterprise|security|other",
    "merged_sources": ["rss", "hackernews"]
  },
  "ai_score": 7.5,
  "ai_reason": "why this matters",
  "ai_summary": "one-line summary",
  "ai_tags": ["llm", "open-source"],
  "impact_score": 4,
  "novelty_score": 3,
  "evidence_score": 4,
  "confidence": "high|medium|low",
  "verification_notes": "string",
  "risks": ["unconfirmed funding amount"]
}
```

Stable ID rule:

```text
id = source_type + ":" + sub_source + ":" + native_id_or_url_hash
```

Use `scripts/hash_payload.py` on canonical URL when native ID is unavailable.

## URL Dedupe Rules

From Horizon `merge_cross_source_duplicates()`:

- Normalize URL host (strip `www.`), path (strip trailing `/`), and fragment.
- Group by normalized URL.
- Keep the richest `content` as primary.
- Merge `metadata` and `merged_sources` from secondary items.
- Append secondary discussion content when it adds signal.

## Topic Dedupe Rules

From Horizon `merge_topic_duplicates()`:

- Run only after score sorting so the highest-scored item becomes the cluster primary.
- Compare title, tags, and one-line summary.
- Merge discussion content from duplicates into the primary item.
- If semantic dedupe is unavailable, fall back to headline similarity and shared entities.

## Balanced Digest

Optional second-stage filter after scoring:

```json
{
  "filtering": {
    "ai_score_threshold": 6.0,
    "max_items": 8,
    "category_groups": {
      "models": { "limit": 3, "categories": ["model", "research"] },
      "products": { "limit": 3, "categories": ["product", "enterprise", "infra"] },
      "policy": { "limit": 2, "categories": ["policy", "security", "funding"] }
    },
    "default_group": "other",
    "default_group_limit": 2
  }
}
```

Apply group limits after threshold filtering and before enrichment.

## Enrichment

Horizon enrichment adds:

- Web background for unfamiliar entities and concepts.
- Community discussion summaries from HN, Reddit, or similar sources when available.

In this skill, `industry_analyst` performs the judgment layer and may request peer input from `source_verifier` when claims need corroboration.

## Multi-Provider AI

Horizon supports Anthropic, OpenAI, Gemini, DeepSeek, Doubao, MiniMax, Ollama, and OpenAI-compatible APIs.

Map provider config into runtime env instead of hardcoding one vendor:

| Provider | Typical env | Default model hint |
| --- | --- | --- |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-*` |
| `openai` | `OPENAI_API_KEY` | `gpt-4.1` |
| `gemini` | `GOOGLE_API_KEY` | `gemini-2.0-flash` |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| `ollama` | local endpoint | `llama3.1` |

The main agent chooses the provider from `data/config.json` or platform runtime. Subagents inherit the configured model; they do not pick providers independently.

## Delivery Difference

Horizon delivers directly after summarization. This skill adds a governance layer Horizon does not provide:

1. Deterministic payload validation.
2. `quality_reviewer` maker-checker pass.
3. Human approval with frozen `payload_hash`.
4. Feishu Base archive before any group publish.
5. Card built only from archived Base read-back.

Never skip the governance layer to mimic Horizon's direct webhook delivery.

## Deterministic Fetch Layer

Implemented scripts:

- `scripts/fetch_sources.py` — orchestrates enabled deterministic sources from config
- `scripts/fetch_rss.py` — RSS/Atom fetch
- `scripts/fetch_hackernews.py` — Hacker News fetch
- `scripts/url_dedupe.py` — cross-source URL merge

Orchestrator flow:

```text
fetch_sources.py
  -> url_dedupe.py
  -> source_collector (official/search gap fill only)
  -> source_verifier
```

`source_collector` must not re-fetch RSS/HN when prefetched items already exist. Hermes may execute `fetch_sources.py` as a bounded executor slice, but the orchestrator still owns state transitions and approval gates.
