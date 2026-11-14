# Project_06 contracts

The current HTTP adapter implements the P08 local `vogue-handoff/0.3` contract at `POST /v1/agents/new-product-agent/runs`. Its input consists of PlanningRequest 1.0, Trend 1.1, and Stock 1.0; the response uses producer `new-product-agent`, schema version `1.0`, and the native P06 result shape.

`http-handoff-v0.3.md` records the current P08-facing compatibility shape. The source schema snapshot lives in P08 and the two repositories must be reviewed together before treating this local-branch alignment as a frozen shared contract. Producer-owned schemas remain with Trend and Stock. P08 owns the P07 review call and planning-board response.
