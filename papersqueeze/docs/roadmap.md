# PaperSqueeze Roadmap

## Objective

Robust Python 3 automation running in venv, **self-contained in scripts/papersqueeze** (no container modifications). Paperless is the system of record - automation only **enriches** and **corrects with strong evidence**.

---

## Design Principles

- **Trust Paperless**: don't alter correspondent/document_type without duplicate verification
- **Evidence + Confidence**: every AI-written field must have confidence and evidence
- **Idempotency**: reprocessing same document must not cause churn
- **Observability**: structured logs with pre-state → decision → diff → post-state
- **Cost Efficiency**: cache by content_hash, escalate only when necessary
- **Model Agnostic**: abstract LLM provider interface - swap Anthropic/OpenAI/Gemini/others via config

---

## LLM Provider Abstraction

The system uses a provider-agnostic interface for all LLM calls:

```
LLMProvider (abstract)
├── AnthropicProvider (default: Haiku/Sonnet)
├── OpenAIProvider (future: GPT-4o-mini/GPT-4o)
├── GeminiProvider (future: Flash/Pro)
└── OllamaProvider (future: local models)
```

**Configuration** (config.yaml):
```yaml
llm:
  provider: "anthropic"  # or "openai", "gemini", "ollama"
  gatekeeper_model: "claude-haiku-4-5-20250514"
  specialist_model: "claude-sonnet-4-20250514"
  vision_model: "claude-sonnet-4-20250514"
```

**Initial implementation**: Anthropic only (Phase 1). Provider interface designed for future expansion.

---

## Architecture (State Pipeline)

### 1. Input
- `doc_id`

### 2. Snapshot (before any change)
- title, created, original_filename
- correspondent_id/name, document_type_id/name
- tags[] (ids + names)
- custom_fields (relevant ones)
- content_len, content_hash, quality metrics
- OCR content

### 3. Template Selection
- Primary: `correspondent_id`
- Secondary: `document_type_id`
- Fallback: conservative default

### 4. Execution
- Deterministic extractors (regex/parsers) → LLM (if needed) → validations → commit decision

### 5. Commit Plan
- Field-level diffs
- Tag-level diffs
- Conditional title update

### 6. Post-Verification
- Re-fetch and confirm final state
- Cleanup and format application

---

## Intelligence Waterfall

### Level -1: Deterministic (zero cost)
- Delegated to `paperless-ngx-postprocessor` as the front-line ruleset engine
- Regex/parsers: dates, amounts, NIF/NIPC, Multibanco (entity/ref), periods, units (kWh/m³)
- If critical fields extracted with high certainty → **skip LLM**

### Level 0: OCR Sanity (filter)
- Metrics: `len(text)`, `ratio_alnum`, `token_hits` (€, EUR, Total, IVA, etc.)
- If OCR is garbage/short/garbled → escalate

### Level 1: Gatekeeper (low cost)
- Fast model (Haiku)
- Extract basic fields, decide if sufficient
- Approve only if:
  - confidence ≥ threshold on critical fields
  - evidence present for each critical field
  - minimum validations pass (e.g., total > 0)

### Level 2: Specialist (reasoning)
- Stronger model (Sonnet)
- When Gatekeeper fails or document is complex
- Additional validations (e.g., gross ≈ net + vat with tolerance)

### Level 3: Vision (nuclear option)
- Convert 1st PDF page to image, request visual read
- **Only** when Level 0 fails (useless OCR) or specific cases
- Guardrails: page limit, retry limit, aggressive cache

---

## Commit Policy

- **Never** overwrite custom_fields/tags by total replacement
- **Title**: update only format, or if empty/placeholder/clearly weak - otherwise preserve
- **Inbox**: remove only when template allows `auto_commit` AND validations pass
- Otherwise: keep Inbox + add `REVIEW_REQUIRED` tag

---

## Templates (data-driven)

Each template defines:
- `selectors` (correspondent_ids, document_type_ids, optional content_regex)
- `fields_to_extract`
- `regex_extractors`
- `llm_schema` (strict JSON)
- `validations[]`
- `commit_policy` (min_confidence, require_evidence, allow_remove_inbox)
- `tags_add/remove`
- `title_template`

Field references use semantic keys (see [custom-fields.md](custom-fields.md)).

---

## Cost & Performance

- **Cache** by `(doc_id, content_hash, template_id, level)`
- Escalate levels only with objective rules
- Pre-fetch metadata (correspondents/types) per run

---

## Observability

Structured logs per document:
```
pre_state → template_selected → extraction_result → validation_result → patch_plan → patch_result → post_state
```

Aggregate metrics:
- Fallback rate
- REVIEW_REQUIRED rate
- Fill-rate by template/correspondent
- Estimated cost per level

---

## Phases

### Phase 1: MVP (robust, no vision)
- Levels -1, 0, 1 (Level -1 handled by postprocessor chain)
- Minimal patch + logs + cache
- Templates by correspondent_id

### Phase 2: Precision
- Level 2 + strong validations + derived fields
- Metrics + tuning per template

### Phase 3: Vision
- Level 3 only with failed OCR + guardrails

---

## Installation (Target)

Self-contained drop-in installation:

1. Copy `papersqueeze/` to Paperless `scripts/` folder
2. Create venv: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
3. Copy `config.example.yaml` → `config.yaml`, edit credentials
4. Configure Paperless-ngx via WebUI (see [paperless-setup.md](paperless-setup.md))
5. Set up post-consume hook: `post_consume.sh` calls PaperSqueeze
6. Done - documents processed automatically on ingest

No container modifications required.
