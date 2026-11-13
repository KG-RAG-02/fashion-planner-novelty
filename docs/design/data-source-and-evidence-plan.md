# Project_06 input and evidence boundary

Project_06 planning accepts only three inputs through [HTTP handoff v0.3](../../contracts/http-handoff-v0.3.md):

| Input | Use |
|---|---|
| User planning request | Defines requested season, category, audience, use, constraints, and required attributes. |
| Trend-agent result | Supplies eligible trend direction and its existing evidence links for the proposed new product. |
| Inventory-agent result | Supplies existing-product facts for planning context; stock images are not sent to the new-product image provider. |

Sales/market results are not part of planning or image-generation input. Synthetic catalog and internal-guideline RAG retrieval, generation, publishing, and evaluation code have been removed. Project_06 does not query synthetic company-like data.

Optional H&M product-photo analysis is external visual inspiration only. It may inform visible design suggestions when configured, but it does not support company-policy, material-composition, quality, sales, demand, or customer-preference claims. Source and image transfer settings are documented in [R2 H&M visual-reference setup](r2-cloud-planning-rag.md).
