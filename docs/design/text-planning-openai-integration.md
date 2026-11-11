# 텍스트 기획 프롬프트 및 Responses API 연결

## 흐름

```text
POST /api/planning-draft
  → R2 synthetic workbench retrieval (when enabled)
  → build_planning_prompt() [system prompt v4 + bounded untrusted JSON]
  → OpenAI Responses API [strict JSON Schema, no tools, store=false]
  → local request/Evidence/schema validation
  → structured draft or deterministic rule fallback
```

System prompt asset `new-product-planner-v4-integrated-planner` classifies claims as user request, evidence observation, proposal, hypothesis, or unknown. Upstream trend, inventory, and sales/market findings are used as already analyzed producer outputs; Project_06 does not recalculate them. The planner may also use authorized R2 text references (currently synthetic and labeled as such) and H&M visual observations (external visual inspiration only). H&M source images, URLs, and catalog rows are not included in the text prompt. Untrusted user, agent, Evidence, visual-analysis, and RAG text is bounded JSON and cannot replace the system role or output contract.

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

`OPENAI_API_KEY` is a fallback key name. The feature is disabled in `.env.example`; enabling it sends bounded user request, trend/inventory results, producer-authored sales-market findings, permitted R2 references, and curated H&M visual observations to OpenAI. Raw H&M photos, URLs, and catalog metadata are excluded from the text prompt. Responses use `store=false` and no tools. This controls response storage and tool access in the API call; it is not a blanket data-transfer approval or a guarantee about provider-side processing/retention. Enable it only where the organization permits the request data to be sent to the configured API provider.

The resulting validated planner draft is passed unchanged into the new-product image workflow. The image provider receives the planner's product definition and visual proposals; raw R2 source text, sales-market payload, and H&M observations are kept out of the image prompt. A separate outfit workflow may use compatible stock images after the new-product image is created.

The adapter uses the Responses API `instructions`, `input`, and `text.format` with strict `json_schema`, following the [OpenAI Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) and [Responses create reference](https://developers.openai.com/api/reference/resources/responses/methods/create). No SDK dependency, tools, retries, or prompt/response logging is added.

## Live verification

On 2026-11-11 the API path was run using a deliberately synthetic 27SS outerwear request. H&M provider transfer and image generation were disabled for the smoke call. With R2 retrieval enabled, the request reached OpenAI using model `gpt-6-astra`, prompt version `new-product-planner-v3-evidence-grounded`, and a ready R2 source with 23 retrieved Evidence references. The result status was `generated`, the request ID matched, and local validation returned no issues. The API response was not saved as a project artifact.

Offline verification: `PYTHONPATH=.:src .venv/bin/pytest -q` → 140 tests passed, 8 subtests passed. Provider adapter tests verify strict-schema request shape, `store=false`, empty tools, refusal/incomplete handling, and redacted HTTP errors. These tests and one synthetic live call do not establish the quality or prompt-injection resistance of future production planning; continue synthetic evals and MD review.
