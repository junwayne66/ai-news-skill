# Feishu Workflow

This workflow uses the Feishu/Lark app configured for `lark-cli` on the OpenClaw host. API submission, callback signature validation, payload hashing, and Base writes should be deterministic scripts, not free-form LLM actions.

Verify exact API paths and permission scopes in the organization's Feishu developer console before deployment. Keep tokens and app secrets in platform secrets.

## Approval Request

Send the news administrator an interactive card or direct message containing:

- Report title and date window.
- Full draft payload that would be sent to the group.
- Source count and confidence summary.
- Buttons: `同意发布` and `驳回重写`.
- Optional text input for rejection feedback.
- Hidden metadata: `job_id`, `payload_hash`, `expires_at`.

Approval card metadata:

```json
{
  "action": "ai_news_approval",
  "job_id": "ai-news-2026-06-04-asia-shanghai",
  "payload_hash": "sha256",
  "expires_at": "2026-06-04T21:00:00+08:00"
}
```

The main agent must freeze the payload before sending the card. Compute the hash with `scripts/hash_payload.py`. If the draft changes later, create a new hash and send a new approval card.

## Approval Decision

Approved callback:

```json
{
  "decision": "approved",
  "job_id": "string",
  "payload_hash": "sha256",
  "operator_user_id": "ou_xxx",
  "decided_at": "ISO-8601"
}
```

Rejected callback:

```json
{
  "decision": "rejected",
  "job_id": "string",
  "payload_hash": "sha256",
  "operator_user_id": "ou_xxx",
  "feedback": "请减少融资新闻，补充模型和基础设施方向。",
  "decided_at": "ISO-8601"
}
```

Rejection handling:

- Store feedback in run state.
- Main agent decides whether to recollect, rerank, or only rewrite.
- Rerun quality review.
- Send a fresh approval card with a new payload hash.

## Group Publishing

Only publish when:

- Internal quality review passed.
- Feishu administrator approved.
- Approval payload hash equals current payload hash.
- Approved items have been archived to Feishu Base.
- The Feishu card was built from fetched archived Base record fields.
- `job_id + card_hash` has not already been published.

Recommended card content:

```text
Card title: AI 行业日报｜YYYY-MM-DD
Header: 时间范围：YYYY-MM-DD HH:mm - YYYY-MM-DD HH:mm（Asia/Shanghai）
Data source: 飞书多维表

1. 新闻标题
摘要：一句话说明发生了什么。
意义：一句话说明为什么值得关注。
来源：Source A（链接） / Source B（链接）
可信度：高

```

Read the archived records with `scripts/fetch_feishu_base_records.py`, build the card with `scripts/build_feishu_card.py`, compute a card hash with `scripts/hash_payload.py`, and send it with `scripts/send_feishu_card.py`.

After sending, store the actual Feishu message ID from the API response in run state and, when possible, update the corresponding Base records with that ID.

## Feishu Base Archive

Create one record per approved final news item before group publishing. Let the archive subagent prepare records, then use `scripts/archive_feishu_base.py` to write them. Recommended table fields:

| Field | Type | Notes |
| --- | --- | --- |
| `日期` | Date | Local date of the report. |
| `标题` | Text | Final headline. |
| `摘要` | Text | Final summary. |
| `意义` | Text | Why it matters. |
| `分类` | Single select | model, product, funding, policy, research, infra, enterprise, security, other. |
| `地区` | Single select | global, china, us, eu, other. |
| `来源` | URL or text | Primary source and supporting links. |
| `发布时间` | DateTime | Source publication time. |
| `可信度` | Single select | high, medium, low. |
| `影响分` | Number | 1-5. |
| `新颖度` | Number | 1-5. |
| `实体` | Multi-select or text | Companies, labs, regulators, products. |
| `Run ID` | Text | `job_id`. |
| `审批状态` | Single select | approved, rejected, republished, failed. |
| `飞书消息 ID` | Text | Group message ID after publish. |
| `归档时间` | DateTime | Archive write time. |

Optional run summary table:

| Field | Type | Notes |
| --- | --- | --- |
| `Run ID` | Text | Unique job ID. |
| `状态` | Single select | completed, failed, partial. |
| `候选数量` | Number | Items collected. |
| `入选数量` | Number | Items published. |
| `审批人` | Text | Administrator ID. |
| `审批时间` | DateTime | Approval time. |
| `群消息 ID` | Text | Published message ID. |
| `失败原因` | Text | Terminal error if any. |

Archive behavior:

- Archive only after administrator approval.
- Build the group card from fetched archived Base fields, not from an unarchived draft.
- Use item idempotency keys to avoid duplicate Base records.
- If archive partially fails, retry failed records only.
- Do not publish the group card until archive succeeds.
