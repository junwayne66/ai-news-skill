# Feishu Workflow

This workflow uses the Feishu/Lark app configured for `lark-cli` on the host. API submission, payload hashing, and Base writes are deterministic scripts, not free-form LLM actions.

## Publishing Policy

**Administrator approval is disabled.** After internal quality review passes:

1. Archive items to Feishu Base.
2. Read archived records back.
3. Build the Feishu card from archived fields.
4. Publish directly to `FEISHU_GROUP_CHAT_ID`.

Never publish from an unarchived draft.

## Group Publishing Gates

Publish only when:

- Internal quality review passed.
- Items have been archived to Feishu Base.
- The Feishu card was built from fetched archived Base record fields.
- Each item's `来源` field contains a valid `https://` URL (rendered as `[原文链接](url)` in the card).
- `job_id + card_hash` has not already been published.

## Card Content

```text
Card title: AI 行业日报｜YYYY-MM-DD  (or AI 行业周报｜YYYY-MM-DD for weekly)
Header: 时间范围：YYYY-MM-DD HH:mm - YYYY-MM-DD HH:mm（Asia/Shanghai）
Data source: 飞书多维表

1. 新闻标题
摘要：一句话说明发生了什么。
意义：一句话说明为什么值得关注。
[原文链接](https://example.com/article)
可信度：高
```

Build flow:

1. `scripts/fetch_feishu_base_records.py`
2. `scripts/build_feishu_card.py` — renders clickable source links
3. `scripts/hash_payload.py`
4. `scripts/send_feishu_card.py`

## Feishu Base Archive

Create one record per final news item before group publishing.

| Field | Type | Notes |
| --- | --- | --- |
| `日期` | Date | Local date of the report. |
| `标题` | Text | Final headline. |
| `摘要` | Text | Final summary. |
| `意义` | Text | Why it matters. |
| `分类` | Single select | model, product, funding, policy, research, infra, enterprise, security, embodied_intelligence, robotics, world_model, other. |
| `地区` | Single select | global, china, us, eu, other. |
| `来源` | URL | **Primary article URL** (`https://...`). Required for card links. |
| `发布时间` | DateTime | Source publication time. |
| `可信度` | Single select | high, medium, low. |
| `影响分` | Number | 1-5. |
| `新颖度` | Number | 1-5. |
| `实体` | Multi-select or text | Companies, labs, products. |
| `Run ID` | Text | `job_id`. |
| `飞书消息 ID` | Text | Group message ID after publish. |
| `归档时间` | DateTime | Archive write time. |

Archive behavior:

- Archive after internal review, before publishing.
- Build the group card from fetched archived Base fields only.
- Use item idempotency keys to avoid duplicate Base records.
- If archive partially fails, retry failed records only.
- Do not publish until archive succeeds.

## Optional: Approval Flow (Legacy)

The MVP private-chat approval flow (`同意发布 <hash>`) is **deprecated** and disabled by default. Do not block publishing on administrator approval unless the user explicitly re-enables it via custom configuration.
