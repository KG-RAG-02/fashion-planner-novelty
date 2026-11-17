# Project_06 prompt assets

This directory contains versioned prompt templates used by P06 workflows. The active `/runs` endpoint currently builds the planning Draft with deterministic rules; it does not call the text-planning model. It does use the concept-image prompt when a real image provider is configured to create the product and outfit visuals from the same product profile.

Runtime code loads prompts through `vogue_npp.domain.prompt_registry`. `manifest.json` selects each component's current version and stable ID. Retired templates are removed from the repository; older result metadata may still refer to their version IDs.

| Component | Current version | Stable prompt ID | Purpose |
|---|---|---|---|
| `text_planning` | `v8` | `new-product-planner-v8-primary-trend` | Opt-in evidence-aware text generation workflow used by the active HTTP `/runs` endpoint when enabled. The data carries only the one primary trend P06 selects (`primary_trend`), and the model is told to plan around it without mixing in other trends. |
| `concept_image` | `v2` | `product-concept-image-prompt-v2-designer` | Product and outfit image prompts derived from the same validated product profile. |

Each version directory has a `system_template.md`, `user_template.md`, and generated `rendered_system.md`. Templates accept only named placeholders; untrusted request data is serialized and bounded before insertion.

## Creating a version

1. Copy the current version directory to a new version directory. Do not edit a released prompt in place.
2. Edit templates and update the component version, directory, and stable ID in `manifest.json`.
3. Run `PYTHONPATH=src python3 scripts/render_prompts.py`.
4. Run prompt registry, planning, and image prompt tests; review the rendered prompt diff.

Prompt changes can alter model behavior. A new version ID alone does not establish improved quality. Keep prompt inputs bounded and preserve the distinction between sourced facts, proposals, and unknown values. The image prompt's shared product-profile hash indicates a common specification; it does not prove that the rendered pixels are identical in design.
