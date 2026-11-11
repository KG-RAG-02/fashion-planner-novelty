# Project_06 prompts

Prompt sources are versioned assets. Runtime code loads these files through `vogue_npp.domain.prompt_registry`; prompt instructions are not maintained inline in the generator modules. `manifest.json` maps each prompt component to an immutable version directory and stable ID stored in generated-result metadata.

| Component | Current version | Stable prompt ID | Purpose |
|---|---|---|---|
| `text_planning` | `v3` | `new-product-planner-v3-evidence-grounded` | Evidence-scoped product planning prompt used by the Responses API adapter |
| `concept_image` | `v2` | `product-concept-image-prompt-v2-designer` | Optional review-only concept image |

Each version directory has a `system_template.md`, `user_template.md`, and generated `rendered_system.md`. The user template contains a named placeholder for untrusted JSON input. Application code serializes and bounds that data before substitution. Do not insert data into the system template.

## Creating a version

1. Copy the component's current version directory to a new version directory. Never edit an already released prompt version in place.
2. Edit the templates and, when needed, update the component's `version`, `directory`, and stable `version_id` in `manifest.json`.
3. Render and validate assets with `PYTHONPATH=src python3 scripts/render_prompts.py`.
4. Run prompt registry, planning, and image prompt tests. Review the rendered system prompt in the diff.
5. Keep the old version directory and ID so prior outputs remain attributable.

Prompt text changes can alter model behavior. They require review and synthetic evaluation; a new version ID alone is not evidence of improved planning quality. The versioned text prompt is connected to the OpenAI Responses API only when `VOGUE_TEXT_GENERATION_ENABLED=true` and an API key is configured.
