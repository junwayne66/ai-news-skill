# Subagent Contracts

## Role Summary

The main agent coordinates these roles. Use actual subagent tools when available. If the runtime has no subagent tool, run each role as an isolated labeled pass with the same inputs and output schema.

Subagents should stay atomic. Each role receives only the relevant slice of context and must return structured data. Do not ask a subagent to perform deterministic work that a script can handle. Subagents may collaborate through main-agent-routed peer messages.

| Role | Purpose | Returns |
| --- | --- | --- |
| `source_collector` | Discover fresh AI industry news candidates. | Candidate `NewsItem` list with raw evidence. |
| `source_verifier` | Validate URLs, dates, source quality, and factual claims. | Verified items, rejected items, risk notes. |
| `dedupe_ranker` | Cluster duplicates and score impact, novelty, and audience relevance. | Ranked shortlist with cluster notes. |
| `industry_analyst` | Explain why each item matters for business, product, research, or policy. | Significance notes and context. |
| `report_editor` | Compose the Feishu-ready Chinese news report. | Draft payload and item summaries. |
| `quality_reviewer` | Audit the draft against quality gates and evidence. | Pass/fail review with required fixes. |
| `archive_record_builder` | Convert approved news items into Feishu Base record fields. | Archive record payloads ready for script execution. |
| `replan_advisor` | Interpret review or administrator rejection feedback. | Minimal rerun plan for the main agent. |

## Main Agent Protocol

The main agent should:

1. Create a task envelope for each role with `job_id`, `RunContext`, required inputs, output schema, and deadline.
2. Query only the memory snippets needed for that role with `scripts/query_memory.py`.
3. Call deterministic scripts before and after role execution when inputs or outputs need normalization, validation, hashing, or idempotency keys.
4. Wait for role returns and inspect `status`, `risks`, `peer_requests`, and `next_request`.
5. Route peer messages between subagents only when the question is atomic and bounded.
6. Ask follow-up questions to the same role when output is incomplete.
7. Reroute tasks when one role uncovers a problem, such as asking `source_collector` for replacement sources after `source_verifier` rejects a candidate.
8. Run `quality_reviewer` after editing and then perform a final main-agent audit before human approval.
9. Freeze the approval payload hash before asking the administrator.
10. After approval, archive approved items first, then build the group card from archived Base fields. Only that card can be sent to the group.

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

Input:

```json
{
  "run_context": {},
  "source_policy": {
    "preferred_sources": ["official blogs", "company newsrooms", "regulator sites", "research labs", "credible tech media"],
    "avoid_sources": ["unsourced social posts", "content farms", "duplicate reposts"]
  },
  "max_candidates": 30
}
```

Output:

```json
{
  "status": "ok",
  "candidates": [
    {
      "headline": "string",
      "raw_summary": "string",
      "primary_source_url": "https://...",
      "published_at": "ISO-8601 or null",
      "source_name": "string",
      "category_guess": "model|product|funding|policy|research|infra|enterprise|security|other",
      "why_candidate": "string"
    }
  ],
  "coverage_notes": "string"
}
```

Collector guidance:

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

Score each verified cluster from 1-5:

- `impact_score`: expected importance to AI industry practitioners.
- `novelty_score`: how new or non-obvious the information is.
- `evidence_score`: source credibility and corroboration.
- `audience_score`: relevance to the target Feishu group.

Return the top items sorted by weighted score. Default weighting:

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
