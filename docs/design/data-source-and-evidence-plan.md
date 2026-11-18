# Project_06 input and evidence boundary

Project_06's `POST /v1/agents/novelty/runs` endpoint accepts the PlanningRequest and P08-supplied Trend/Stock results. The supported request and response are compared with P08's local `novelty-handoff` contract; see the [service runbook](prototype-runbook.md).

| Input | Use |
|---|---|
| User planning request | Defines requested season, category, audience, use, constraints, and required attributes. |
| Trend-agent result | Supplies eligible trend direction and its existing evidence links for the proposed new product. |
| Stock-agent result | Supplies existing-product facts for planning context; stock photos are not sent to the new-product image provider. |

Sales/market results are not part of planning or image-generation input. P08 calls P07 only after receiving the P06 draft. Project_06 does not query synthetic company-like operational data.
