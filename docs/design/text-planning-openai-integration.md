# Text and image provider status

The active `/v1/agents/new-product-agent/runs` path uses the P06 analysis pipeline with an opt-in `PromptedConceptGenerator`. Set `VOGUE_TEXT_GENERATION_ENABLED=true` to call the OpenAI Responses adapter using the shared `LLM_API_KEY`; otherwise the route remains deterministic. Provider failures and invalid structured output fall back to `RuleBasedConceptGenerator` and are reported in `generation_metadata` and validation issues.

P06 visual generation is controlled by `VOGUE_DRAFT_IMAGE_PROVIDER=openai` and image credentials. P06 has no synthetic image provider mode. Offline tests mock the image provider and make no paid request. Product/outfit generation occurs only when the real provider is explicitly configured.
