# Prompt injection and model boundary

## Active `/runs` behavior

- The active HTTP route uses `RuleBasedConceptGenerator`; it does not call a text model or agent tools.
- Product and outfit image prompts are built from the validated draft profile. Untrusted values are encoded as bounded JSON data. The image provider has no application tools, filesystem access, or agent-call interface. The active image settings are `VOGUE_DRAFT_IMAGE_PROVIDER` and `OPENAI_API_KEY`; there is no separate image-enable flag.
- Provider request bodies and credentials are not logged. Provider errors are reduced to safe error codes.
- P06 does not configure a production retrieval corpus, call P07, or render a planning board.

## Separately tested components

`PromptedConceptGenerator` and the OpenAI Responses adapter are standalone components covered by mock tests; the `/runs` HTTP route does not select them. If a future route enables text generation, it must preserve request isolation, validate output and Evidence IDs against the current request, and avoid logging prompts or secrets.

## Limits

Prompt framing is defense in depth, not a guarantee against model influence. Evidence ID membership checks do not prove source authenticity, authorization, or semantic support. Do not send sensitive data to an external model without an approved data-transfer policy.
