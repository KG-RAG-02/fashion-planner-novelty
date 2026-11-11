# 텍스트 기획 프롬프트 및 Responses API 연결

## 흐름

```text
POST /api/planning-draft
  → R2 synthetic workbench retrieval (when enabled)
  → build_planning_prompt() [system prompt v3 + bounded untrusted JSON]
  → OpenAI Responses API [strict JSON Schema, no tools, store=false]
  → local request/Evidence/schema validation
  → structured draft or deterministic rule fallback
```

System prompt asset `new-product-planner-v3-evidence-grounded` classifies claims as user request, evidence observation, proposal, hypothesis, or unknown. It directs the model to keep synthetic workbench results visibly synthetic, treat inventory as a point-in-time fact, leave Project_07 market details opaque, preserve uncertainty, and ask for MD validation where evidence is missing. Untrusted user, agent, Evidence, and RAG text is bounded JSON in the user input and cannot replace the system role or output contract.

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

`OPENAI_API_KEY` is a fallback key name. The feature is disabled in `.env.example`; enabling it means each eligible planning request can send the bounded user request, eligible trend/inventory fields, permitted planning references, and opaque sales-market status to OpenAI. Detailed Project_07 results and H&M photos are excluded from the text prompt. Responses use `store=false` and no tools. This controls response storage and tool access in the API call; it is not a blanket data-transfer approval or a guarantee about provider-side processing/retention. Enable it only where the organization permits the request data to be sent to the configured API provider.

The adapter uses the Responses API `instructions`, `input`, and `text.format` with strict `json_schema`, following the [OpenAI Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) and [Responses create reference](https://developers.openai.com/api/reference/resources/responses/methods/create). No SDK dependency, tools, retries, or prompt/response logging is added.

## Live verification

On 2026-11-11 the API path was run using a deliberately synthetic 27SS outerwear request. H&M provider transfer and image generation were disabled for the smoke call. With R2 retrieval enabled, the request reached OpenAI using model `gpt-6-astra`, prompt version `new-product-planner-v3-evidence-grounded`, and a ready R2 source with 23 retrieved Evidence references. The result status was `generated`, the request ID matched, and local validation returned no issues. The API response was not saved as a project artifact.

Offline verification: `PYTHONPATH=.:src .venv/bin/pytest -q` → 140 tests passed, 8 subtests passed. Provider adapter tests verify strict-schema request shape, `store=false`, empty tools, refusal/incomplete handling, and redacted HTTP errors. These tests and one synthetic live call do not establish the quality or prompt-injection resistance of future production planning; continue synthetic evals and MD review.
