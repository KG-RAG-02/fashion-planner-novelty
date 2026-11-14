# Project_06 prompts

Prompt sources are versioned assets. Runtime code loads them through `vogue_npp.domain.prompt_registry`; `manifest.json` selects the current version and stable ID. Retired prompt templates are removed from this repository; old result metadata may still contain their version IDs.

| Component | Current version | Stable prompt ID | Purpose |
|---|---|---|---|
| `text_planning` | `v7` | `new-product-planner-v7-current-inputs-only` | Standalone evidence-aware text generator; the active `/runs` endpoint currently selects the deterministic rule generator. |
| `concept_image` | `v2` | `product-concept-image-prompt-v2-designer` | Product and outfit image prompts based on the same product profile. |

Each version directory has a `system_template.md`, `user_template.md`, and generated `rendered_system.md`. Templates accept only named placeholders; untrusted request data is serialized and bounded before insertion.

## Creating a version

1. Copy the current version directory to a new version directory. Do not edit a released prompt in place.
2. Edit templates and update the component version, directory, and stable ID in `manifest.json`.
3. Run `PYTHONPATH=src python3 scripts/render_prompts.py`.
4. Run prompt registry, planning, and image prompt tests; review the rendered prompt diff.

Prompt changes can alter model behavior. A new version ID alone does not establish improved quality. The text prompt/provider are not selected by the active HTTP `/runs` route.
