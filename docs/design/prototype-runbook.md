# Project_06 planning API

## Run locally

From the repository root:

```bash
VOGUE_HTTP_MODE=local PYTHONPATH=src python3 -m vogue_npp.prototype.server
```

The service binds to `127.0.0.1:8767` by default. The canonical `/runs` route also requires `Authorization: Bearer` matching `VOGUE_AGENT_SERVICE_BEARER_TOKEN` in local mode. `VOGUE_HTTP_MODE=local` is required and permits only loopback. The default port is distinct from Project_08's UI (8765) and Project_07's local HTTP adapter (8766). It does not serve a browser UI; Project_08 owns the local interface. Stop the service with `Ctrl+C`.

## API boundary

`POST /api/planning-draft` accepts planning request, trend, and inventory inputs, then returns the P06 draft and new-product image. It does not query upstream source systems or require P07 review output.

The versioned handoff is implemented at `POST /v1/agents/new-product-agent/runs`; see [HTTP handoff v0.3](../../contracts/http-handoff-v0.3.md) for request/response fields, supported versions, service mode and errors. The legacy planning route remains available. P08 submits the full P06 response to `POST /v1/agents/new-product-agent/sales-market-reviews`; P06 validates and maps the profile to P07, then returns P07's envelope.

The API also supports existing planning brief and image variant operations. Generated P06 product images are served from `/api/generated-images/{filename}`. P06 does not generate planning-board images. SQLite state and generated image files are local runtime artifacts; this service does not serve the browser UI.

## Image generation

Set `VOGUE_IMAGE_GENERATION_ENABLED=true` and `LLM_API_KEY` in the runtime environment. Image generation is opt-in per API request. Generated images are exploratory design material and do not validate fit, materials, demand or production feasibility.

## Project_07 data products

Project_06 does not load sales, market, H&M historical or operations datasets. Those source and analysis responsibilities belong to Project_07.
