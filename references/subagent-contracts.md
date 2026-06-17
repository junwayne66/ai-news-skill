# Subagent Contracts

## Horizon Stage Mapping

| Horizon stage | Subagent role | Loop state stage |
| --- | --- | --- |
| Fetch | `fetch_sources` + `url_dedupe` scripts, then `source_collector` gap fill | `fetching`, `url_deduping` |
| URL dedupe | `url_dedupe` script (primary) | `url_deduping` |
| AI score + filter | `dedupe_ranker` | `scoring`, `balancing` |
| Topic dedupe | `dedupe_ranker` | `topic_deduping` |
| Verify | `source_verifier` | during `scoring` / `url_deduping` |
| Enrich | `industry_analyst` | `enriching` |
| Summarize | `report_editor` | `drafting` |
| Review | `quality_reviewer` | `internal_review` |
| Archive fields | `archive_record_builder` | `archiving` |
| Replan | `replan_advisor` | `replanning` |

Hermes may execute `source_collector`, `dedupe_ranker`, and `industry_analyst` slices when dispatched by the orchestrator. The orchestrator retains approval and publish authority.

## Role Summary

The orchestrator coordinates these roles. Use platform subagent tools when available:

- OpenClaw subagent tool
- Claude Code / Cursor `Task` tool
- Hermes ACP delegation for bounded execution slices

If no subagent tool exists, run each role as an isolated labeled pass with the same schema.

Subagents should stay atomic. Each role receives only the relevant slice of context and must return structured data. Do not ask a subagent to perform deterministic work that a script can handle. Subagents may collaborate through main-agent-routed peer messages.

| Role | Purpose | Returns |
| --- | --- | --- |
| `source_collector` | Fill discovery gaps after deterministic fetch (`official`, `search`, and other non-script sources). | Additional candidate `NewsItem` list with raw evidence. |
| `source_verifier` | Validate URLs, dates, source quality, and factual claims. | Verified items, rejected items, risk notes. |
| `dedupe_ranker` | Cluster duplicates and score impact, novelty, and audience relevance. | Ranked shortlist with cluster notes. |
| `industry_analyst` | Explain why each item matters for business, product, research, or policy. | Significance notes and context. |
| `report_editor` | Compose the Feishu-ready Chinese news report. | Draft payload and item summaries. |
| `quality_reviewer` | Audit the draft against quality gates and evidence. | Pass/fail review with required fixes. |
| `archive_record_builder` | Convert approved news items into Feishu Base record fields. | Archive record payloads ready for script execution. |
| `replan_advisor` | Interpret review or administrator rejection feedback. | Minimal rerun plan for the main agent. |

## Orchestrator Protocol

The orchestrator should:

1. Read `loop_state.json` before dispatching any role.
2. Create a task envelope with `job_id`, `RunContext`, required inputs, output schema, and `loop_state_path`.
3. Query role memory with `scripts/query_memory.py`.
4. Call deterministic scripts before and after role execution.
5. Write `loop_state` after each verified stage transition.
6. Route peer messages only for atomic bounded questions.
7. Enforce maker-checker: never skip `quality_reviewer` before approval.
8. Freeze `payload_hash` before administrator review.
9. After approval, archive first; build the group card only from Base read-back.
10. On Hermes handoff, pass only the envelope and expect structured JSON back.

## Message Envelope

All agent/subagent communication should use this envelope:

```json
{
  "job_id": "string",
  "from_role": "main_agent",
  "to_role": "source_verifier",
  "action": "assign_task|request_peer_input|peer_response|return_result|request_memory",
  "status": "ok|needs_input|blocked|failed",
  "context_refs": ["memory-snippet-id"],
  "payload": {},
  "evidence": [{"url": "https://...", "note": "short support note"}],
  "risks": [{"severity": "low|medium|high", "detail": "string"}],
  "peer_requests": [
    {
      "to_role": "dedupe_ranker",
      "question": "Are these two URLs the same story?",
      "item_ids": ["item_a", "item_b"]
    }
  ],
  "next_request": "string or null"
}
```

The main agent is the router. A subagent should not receive the full task history just to answer a peer question.

## Source Collector

The orchestrator must run deterministic fetch scripts before dispatching this role:

```bash
scripts/fetch_sources.py --config data/config.json --input /tmp/run-context.json --include-collector-candidates > /tmp/prefetched.json
scripts/url_dedupe.py --input /tmp/prefetched.json > /tmp/prefetched-deduped.json
```

Input:

```json
{
  "run_context": {},
  "prefetched_items": [],
  "collector_candidates": [],
  "discovery_policy": {
    "official": {"enabled": true, "urls": ["https://www.anthropic.com/news"]},
    "search": {"enabled": true, "queries": ["AI model release last 24 hours"]},
    "preferred_sources": ["official blogs", "company newsrooms", "regulator sites", "research labs", "credible tech media"],
    "avoid_sources": ["unsourced social posts", "content farms", "duplicate reposts"]
  },
  "max_candidates": 30,
  "max_additional_candidates": 12
}
```

Output:

```json
{
  "status": "ok",
  "prefetched_count": 18,
  "additional_candidates": [
    {
      "headline": "string",
      "raw_summary": "string",
      "primary_source_url": "https://...",
      "published_at": "ISO-8601 or null",
      "source_name": "string",
      "category_guess": "model|product|funding|policy|research|infra|enterprise|security|other",
      "why_candidate": "string",
      "prefetched": false
    }
  ],
  "candidates": [],
  "coverage_notes": "string"
}
```

Collector guidance:

- Do not re-fetch RSS/Hacker News when `prefetched_items` already contains them.
- Only discover from `official` and `search` (or other non-deterministic channels) in `discovery_policy`.
- Skip URLs already present in `prefetched_items` after `url_dedupe`.
- Merge `prefetched_items` and `additional_candidates` into final `candidates` without duplicate primary URLs.
- Prefer primary sources. Use credible media to discover leads, then look for primary confirmation.
- Include funding, product launches, model releases, policy/regulation, enterprise adoption, chips/infrastructure, safety/security, and high-impact research.
- Do not include an item only because it is viral.

## Source Verifier

Input: collector candidates and run context.

Output:

```json
{
  "status": "ok",
  "verified_items": [],
  "rejected_items": [
    {
      "headline": "string",
      "reason": "outside_window|broken_source|duplicate|low_credibility|unsupported_claim"
    }
  ],
  "risks": []
}
```

Verifier guidance:

- Confirm the publication date and source identity using available evidence; let deterministic scripts perform strict date-window and required-field validation afterward.
- Mark secondary-only claims as medium or low confidence.
- Flag numbers such as funding amounts, benchmark scores, revenue, user counts, or legal penalties unless clearly sourced.
- Keep concise verification notes that the editor can turn into source footnotes.

## Dedupe Ranker

Score each verified cluster using Horizon-style 0-10 `ai_score` plus 1-5 component scores:

- `impact_score`: importance to AI practitioners
- `novelty_score`: how new or non-obvious
- `evidence_score`: source credibility and corroboration
- `audience_score`: relevance to the target Feishu group

Filter with `ai_score_threshold` from `data/config.json` (default 6.0). Apply `category_groups` and `max_items` for balanced digest when configured.

Default weighting for final rank within shortlist:

```text
impact 35%, evidence 25%, audience 25%, novelty 15%
```

## Industry Analyst

For each ranked item, return:

```json
{
  "item_id": "string",
  "why_it_matters": "1-2 Chinese sentences",
  "stakeholders": ["developers", "product teams", "investors", "policy teams"],
  "watch_next": "what to monitor next, or null"
}
```

Keep analysis grounded in verified evidence. Do not invent strategy implications.

## Report Editor

Draft the Feishu message in Chinese with this shape:

```text
AI 行业日报｜YYYY-MM-DD
时间范围：YYYY-MM-DD HH:mm - YYYY-MM-DD HH:mm（Asia/Shanghai）

1. 标题
摘要：...
意义：...
来源：Source A / Source B
可信度：高/中/低

今日值得关注：...
```

Rules:

- Keep each item compact enough for chat reading.
- Preserve source links.
- Use neutral language for uncertainty.
- Do not include internal task notes or subagent names in the public report.

## Quality Reviewer

Return:

```json
{
  "status": "pass|fail",
  "blocking_issues": [
    {
      "item_id": "string",
      "gate": "source|date|duplicate|claim|tone|format|approval_safety",
      "required_fix": "string"
    }
  ],
  "non_blocking_suggestions": [],
  "approval_ready": true
}
```

The reviewer should be strict. A shorter verified report is better than a fuller but shaky report.

## Archive Record Builder

Prepare one record per approved news item and one optional run summary record. The actual Feishu Base write must be done by `scripts/archive_feishu_base.py`. The group card will be built from these archived fields after the script succeeds.

Return:

```json
{
  "status": "ok|failed",
  "records": [
    {
      "item_id": "string",
      "fields": {
        "日期": "YYYY-MM-DD",
        "标题": "string",
        "摘要": "string",
        "意义": "string",
        "来源": "https://...",
        "可信度": "high|medium|low",
        "分类": "model|product|funding|policy|research|infra|enterprise|security|other",
        "Run ID": "string"
      }
    }
  ],
  "errors": []
}
```

## Replan Advisor

Use this role only when internal review fails or the Feishu administrator rejects the draft.

Return:

```json
{
  "status": "ok",
  "rerun_steps": ["source_collector|source_verifier|dedupe_ranker|industry_analyst|report_editor|quality_reviewer"],
  "reason": "short explanation",
  "minimal_feedback": "instruction to pass to the rerun role"
}
```

The main agent decides whether to accept the replan. The advisor does not restart work by itself.
