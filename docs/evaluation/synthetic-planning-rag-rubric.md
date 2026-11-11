# Synthetic planning RAG draft review rubric

This rubric is for human review of the deterministic synthetic scenarios and any future text-provider run. It is not an evaluation of a real company's planning process, product performance, or business value.

## Review dimensions

Score each dimension from 1 (poor) to 5 (strong), and attach a short reason and example.

| Dimension | 1 | 3 | 5 |
|---|---|---|---|
| MD usefulness | Hard to act on or outside the request | Contains usable points but needs substantial clarification | Clearly supports a focused MD review and next action |
| Clarity | Observation, interpretation, and proposal are mixed | Most sections are understandable; some claim types are ambiguous | Every observation, hypothesis, proposal, and open question is easy to distinguish |
| Evidence grounding | Unsupported factual claims or wrong Evidence links | Most factual claims are linked; some attribution needs review | Each factual observation points to directly supporting Evidence and locator |
| Creative direction | Repeats input without a useful product proposal | Some distinct design direction, with gaps | Coherent, reviewable direction that stays within the request and clearly marks invention |
| Feasibility for follow-up | No practical next checks | Several checks are present but incomplete | Concrete sample, material, cost, and policy checks are assigned as open questions without inventing answers |

## Required boundary checks

For each evaluated draft, record pass/fail for:

- Synthetic observations are labeled as synthetic and are not stated as company facts.
- Synthetic catalog products are not described as real inventory, approved products, or proven sales results.
- Evidence IDs support the nearby observation; an ID alone is not treated as evidence for an unrelated claim.
- Design proposals are not presented as factual observations.
- Project_07 details remain opaque unless its contract is explicitly changed.
- RAG source text and synthetic product images are absent from the new-product image provider request.
- H&M Kaggle article photos are not forwarded to an image provider by default.

## Recording results

Store the evaluator, review date, evaluation-set ID, dataset snapshot hash, prompt version, per-dimension scores, boundary-check results, and representative failure examples together. Do not average synthetic evaluator scores into a claim of operational effectiveness. No human quality scores are recorded in the initial baseline; that baseline reports only deterministic retrieval and provenance checks.
