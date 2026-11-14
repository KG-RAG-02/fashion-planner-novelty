# Text and image provider status

The active `/v1/agents/new-product-agent/runs` path uses `RuleBasedConceptGenerator` and the P06 analysis pipeline. It does not make a text-model request. `PromptedConceptGenerator` and its Responses API provider remain separately tested components and are not selected by this endpoint.

P06 visual generation is controlled by `VOGUE_DRAFT_IMAGE_PROVIDER=openai` and image credentials. P06 has no synthetic image provider mode. Offline tests mock the image provider and make no paid request. Product/outfit generation occurs only when the real provider is explicitly configured.
