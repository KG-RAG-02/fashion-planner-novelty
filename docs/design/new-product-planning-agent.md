# Project_06 new-product planning agent

## Current runtime behavior

Project_06 creates a reviewable product-planning draft from exactly three inputs: the user planning request, Trend Agent result, and Inventory Agent result. The canonical API contract is [HTTP handoff v0.3](../../contracts/http-handoff-v0.3.md).

The Sales Market result object is not part of the planning or image-generation request. A separate optional post-draft review proxy may call Project_07 after planning; this is not an input to the planner or image generator.

Project_06 does not query synthetic catalog, company guideline, precedent, or taxonomy datasets. Those offline fixtures and tools do not enter the runtime prompt or planning context. Optional H&M photo analysis from R2 is treated only as external visual inspiration and is separated from company facts.

The new-product image is generated from the product draft informed by the request and eligible trend results. P06 does not generate outfit or planning-board images. Optional H&M visual references are analyzed separately from company product facts. See the [R2 visual-reference boundary](r2-cloud-planning-rag.md) and [text-planning prompt integration](text-planning-openai-integration.md) for details.
