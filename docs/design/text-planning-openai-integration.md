# 텍스트 기획 프롬프트 및 Responses API 연결

## 흐름

```text
POST /api/planning-draft
  → optional external H&M visual-reference analysis
  → build_planning_prompt() [system prompt v5 + bounded untrusted JSON]
  → OpenAI Responses API [strict JSON Schema, no tools, store=false]
  → local request/Evidence/schema validation
  → structured draft or deterministic rule fallback
```

System prompt asset `new-product-planner-v5-request-trend-stock` classifies claims as user request, evidence observation, proposal, hypothesis, or unknown. Only the planning request, trend result, and inventory result are planning inputs. Synthetic R2 catalog and guideline references and the sales/market result are not used. H&M visual observations, when enabled, remain separate external visual inspiration. H&M source images, URLs, and catalog rows are not included in the text prompt. Untrusted user, agent, Evidence, and visual-analysis text is bounded JSON and cannot replace the system role or output contract.

The generation parser checks the exact output keys, request ID, claim types and lengths, known Evidence IDs, and domain validation. It does not establish that a producer is authentic or that an Evidence item semantically supports a claim; the prompt and human review remain necessary. Failed API requests or outputs return the deterministic rule draft. `generation_metadata.error_code` contains only a stable code, never provider response text.

## API request and settings

Set the following in `.env` or the runtime secret store:

```dotenv
VOGUE_TEXT_GENERATION_ENABLED=true
VOGUE_TEXT_GENERATION_MODEL=gpt-6-astra
VOGUE_TEXT_GENERATION_TIMEOUT_SECONDS=60
VOGUE_TEXT_GENERATION_MAX_OUTPUT_TOKENS=3000
LLM_API_KEY=<secret>
```

`OPENAI_API_KEY` is a fallback key name. The feature is disabled in `.env.example`; enabling it sends bounded user request and trend/inventory results, plus optional H&M visual observations, to OpenAI. Synthetic company data and Sales Market findings are not included. Raw H&M photos, URLs, and catalog metadata are excluded from the text prompt. Responses use `store=false` and no tools. This controls response storage and tool access in the API call; it is not a blanket data-transfer approval or a guarantee about provider-side processing/retention. Enable it only where the organization permits the request data to be sent to the configured API provider.

The resulting validated planner draft is passed unchanged into the new-product image workflow. The image provider receives the planner's product definition and visual proposals; synthetic company data, Sales Market payloads, and stock images are not used.

The adapter uses the Responses API `instructions`, `input`, and `text.format` with strict `json_schema`, following the [OpenAI Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) and [Responses create reference](https://developers.openai.com/api/reference/resources/responses/methods/create). No SDK dependency, tools, retries, or prompt/response logging is added.

## Live verification

Historical smoke results below predate removal of synthetic planning RAG and do not describe the current runtime flow.

Offline verification: `PYTHONPATH=.:src .venv/bin/pytest -q` → 140 tests passed, 8 subtests passed. Provider adapter tests verify strict-schema request shape, `store=false`, empty tools, refusal/incomplete handling, and redacted HTTP errors. These tests and one synthetic live call do not establish the quality or prompt-injection resistance of future production planning; continue synthetic evals and MD review.
