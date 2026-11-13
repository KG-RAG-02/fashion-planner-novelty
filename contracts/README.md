# Project_06 contracts

This folder contains the Project_06-specific implementation of the shared agent-run contract, including accepted producer schema versions and the input-normalization behavior. It does not redefine the producer schemas owned by Project_07, Trend, or Stock.

- [Project_06 HTTP handoff v0.3](http-handoff-v0.3.md) (current; planning request, trend, and inventory only)
- Project_07 owns its producer result and shared-envelope JSON Schemas in its repository's `contracts/schemas/`.

Superseded v0.1 and v0.2 contract documents and fixtures were removed. The active P06 runtime contract is defined by the v0.3 adapter and its tests.
