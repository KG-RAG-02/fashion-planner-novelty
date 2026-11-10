# Prompt injection boundary for planning

Status: implementation note; text generation remains deterministic. These controls reduce accidental instruction mixing in the optional image-generation path; they do not guarantee immunity from model influence.

## Current data and model paths

- The production API defaults to `RuleBasedConceptGenerator`. `PromptedConceptGenerator` now provides a versioned system prompt, bounded untrusted JSON context, strict output parsing, Evidence allowlist checks, and deterministic fallback. It is available behind the `VOGUE_TEXT_GENERATION_ENABLED` setting and an injectable provider seam. No concrete text LLM provider or agent tool-calling integration is configured, so enabling the flag alone returns the rule-based fallback with an unavailable status.
- `retrieve_planning_knowledge` defaults to `EmptyKnowledgeRetriever` and an empty source policy. The API server does not configure a production corpus. When an authorized retriever is explicitly supplied by a caller, `planning_retrieval.py` filters results by source allowlist, permission status, permitted use, and evidence lookup IDs.
- Image generation is the current external model path. It requires both server-side image generation enablement and an explicit request flag. Planning-board generation additionally requires a successfully generated reference image and a separate request flag.
- User text, upstream fields, Evidence quotes, and retrieved reference text included in image prompts are serialized as bounded JSON data. Newlines, quotes, and control characters are escaped; individual strings and aggregate prompt data are capped. Trusted prompt instructions tell the image model to treat JSON values as data and ignore embedded instructions.
- The image API has no application tools, filesystem access, or agent-call interface. API request logging omits request bodies. Provider errors are converted to stable error codes rather than returning provider response bodies.

## Provenance and limits

The deterministic draft validator checks request ID consistency and that cited Evidence IDs occur in the current input context. This is a membership check, not proof that a producer is authentic, the source is authorized, or an Evidence item supports a claim. Raw upstream payloads remain preserved for traceability; producer IDs, statuses, and Evidence IDs inside those payloads are claims from the caller unless verified by a future authenticated contract boundary.

JSON framing and prompt instructions are defense in depth. A generative image model can still be influenced by malicious content in a value, and the image API accepts one combined prompt string rather than separate privileged and untrusted message roles. Do not describe the current path as prompt-injection-proof. Sensitive information must not be included in inputs sent for image generation.

## Requirements before adding a text LLM or tools

1. Keep system/developer policy outside user, upstream, and retrieved content; pass those sources as separately typed, bounded data.
2. Use no tools, network, or file permissions by default. Any approved tool requires a narrow allowlist and server-side authorization independent of model output.
3. Validate structured output against a fixed schema, allowed status values, the active request ID, and Evidence IDs from the current request. Reject or mark invalid outputs for review; never treat model-created IDs or source metadata as evidence.
4. Keep requests isolated, preserve source provenance, and avoid logging prompts, credentials, or complete sensitive payloads.
5. Add offline adversarial tests for instruction-like user text, retrieved passages, forged Evidence IDs, malformed/oversized input, and outputs that cross the request boundary before enabling the model in production.
