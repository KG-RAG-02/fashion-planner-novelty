# Project_07 handoff implementation note

Status: proposal only; not a ratified shared wire contract. The matching schema copy in `contracts/schemas/proposals/` is informational until Project_07, Project_06, and the designated contract steward approve it.

Project_06 treats the complete Project_07 result as an opaque mapping. It checks the request ID, agent identity, and top-level status, preserves the original mapping in the planning draft, and recursively carries Evidence IDs plus block-level limitations, errors, and missing-data notes into review context. It does not aggregate sales or market values, compute margins, reinterpret metrics, or convert missing data into zero.

The handoff transport and schema version remain undecided. The local `/api/planning-draft` is a prototype adapter, not a production service contract.
