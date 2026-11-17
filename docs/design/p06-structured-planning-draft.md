# P06 structured product profile

P06 keeps a typed `ProductProfile` inside the planning draft. P08 receives it as `result.draft.product_profile` and uses it to construct the P07 `/reviews` request. P06 does not project or send a P07 payload itself.

## Profile model

Each profile claim carries a `value`, `kind`, and `evidence_ids`. Unknown or unverified properties remain null/unknown; conflicting inputs stay in conflict/limitation fields rather than being silently resolved. Evidence IDs must come from the current request.

```json
{
  "product_profile": {
    "category": {"value": "Outerwear", "kind": "user_requested", "evidence_ids": []},
    "product_type": {"value": null, "kind": "unknown", "evidence_ids": []},
    "gender": {"value": null, "kind": "unknown", "evidence_ids": []},
    "season": {"value": "spring/summer 2027", "kind": "user_requested", "evidence_ids": []},
    "material": {"value": null, "kind": "unknown", "evidence_ids": []}
  }
}
```

P08 reads `value` from the profile and sends `category` plus available `product_type`, `gender`, `season`, and `material` to P07. This is the consumer mapping in P08; it is not a P06 review bridge.

## One trend per draft

The draft is planned around one primary trend, chosen deterministically among the usable trend candidates (named, evidenced, not contradicting the requested season/category/market/channel): most evidence-linked design attributes, then most Evidence IDs (candidate, description and attribute), then earliest input order. The rule-based concept, opportunity, attributes and profile and the text-LLM input use only that trend. `draft.trend_basis` records it (`source_style_id`, `name`, `selection_rule` `most_evidence_linked_design_attributes/1`, `evidence_ids`, `design_attributes`, `candidates_considered`) and is `null` when no usable trend exists. The visuals follow the profile, so they carry only that trend's attributes. When the primary trend has two or more evidence-linked colours, the profile colour is the first evidence-linked colour in input order (a requested colour is kept); the text-LLM path applies the same rule, so the images and the P07 review input get that one colour. Material and silhouette are promoted only when they have exactly one value.

## One source for draft and visuals

The active `/runs` route first produces the analyzed draft and its profile. It then passes that same profile to the product and outfit prompt builder. Unspecified material, color, fit and decoration are not asserted as fixed facts in the visual prompt. The prompt model metadata and artifact status are included in `draft.visuals`.

Product and outfit images are generated only with the real OpenAI image provider explicitly configured. Tests use a mock provider and do not create synthetic image artifacts. Missing provider configuration yields `skipped`; unsupported provider, generation, or persistence errors yield `failed` and an overall `partial` response. Both image prompts include the same canonical profile (with its usable `details`) and return a matching `product_specification_sha256`. The calls are sequential: the outfit is an Images Edit API call whose reference input is the stored product image (`reference_image_sha256` on the outfit visual), and it is skipped with `OUTFIT_REFERENCE_UNAVAILABLE` when no product image exists. This keeps both visuals on one garment, but pixel-level identity is not verified automatically. P06 does not create the P08 planning board.

## P08 compatibility

The implementation is aligned to P08's local `vogue-handoff/0.3` `/runs` request and result schemas. P06's native response includes `product_profile`, `planning_analysis`, `input_evidence`, `compatibility`, status fields, and product/outfit visual summaries. Artifact refs use `artifact://p06/images/<sha256>.<ext>` and include immutable, media type, byte size and SHA-256 metadata; P08 imports and verifies them through the shared volume.

This is a local branch compatibility result, not a frozen shared contract. Keep P08 request/result schemas and artifact mount settings aligned before deployment.
