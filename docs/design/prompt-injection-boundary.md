# Prompt injection and model boundary

## Active `/runs` behavior

- The active HTTP route uses an opt-in `PromptedConceptGenerator` with a deterministic fallback; it does not call agent tools.
- Product and outfit image prompts are built from the validated draft profile. Untrusted values are encoded as bounded JSON data. The image provider has no application tools, filesystem access, or agent-call interface. The active image settings are `NOVELTY_DRAFT_IMAGE_PROVIDER` and `LLM_API_KEY`; there is no separate image-enable flag.
- Provider request bodies and credentials are not logged. Provider errors are reduced to safe error codes.
- P06 does not configure a production retrieval corpus, call P07, or render a planning board.

## Separately tested components

The `/runs` route enables text generation only with `NOVELTY_TEXT_GENERATION_ENABLED=true`. It preserves request isolation, validates output and Evidence IDs against the current request, and falls back to the deterministic draft without logging prompts or secrets.

## Limits

Prompt framing is defense in depth, not a guarantee against model influence. Evidence ID membership checks do not prove source authenticity, authorization, or semantic support. Do not send sensitive data to an external model without an approved data-transfer policy.
