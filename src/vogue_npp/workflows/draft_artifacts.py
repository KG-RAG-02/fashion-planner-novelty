"""Content-addressed draft visuals with durable request ownership and replay."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class ImageRunAlreadyClaimed(RuntimeError):
    """A paid image attempt for this request has started but has no replayable response yet."""


class RequestReplayConflict(ValueError):
    """A request ID was already committed with a different input payload."""


class OpenAIDraftImageProvider:
    """Explicitly opted-in product/outfit images: the product is generated, the outfit edits that product image.

    Sequential by design (VOGUE decision 2026-11-17): the outfit call receives the generated product image as its
    reference input, so both visuals show the same garment. Both prompts carry the same product specification.
    The outfit shows the new product worn with one existing stock item (VOGUE decision 2026-11-17,
    domain/outfit_companion.py): its photograph is input image 2 when the stock result carried one, and its
    stock attributes are described in the prompt either way.
    """
    prompt_version = "p06-draft-visuals/4"
    _ROLE_PHRASES = {"lower_body": " as the bottom", "upper_body": " as the top"}

    def __init__(self, api_key: str, model: str, timeout_seconds: int = 180):
        from .image_generation import OpenAIImageEditProvider, OpenAIImageProvider
        self._provider = OpenAIImageProvider(api_key=api_key, model=model, timeout_seconds=timeout_seconds)
        self._editor = OpenAIImageEditProvider(api_key=api_key, model=model, timeout_seconds=timeout_seconds)
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(self, kind: str, product: dict, request_id: str, reference_image: bytes | None = None,
                 companion: dict | None = None) -> bytes:
        """``companion``: {"specification": dict, "role": str | None, "image": bytes | None, "media_type": str}."""
        from ..domain.prompt_registry import load_prompt
        from .image_generation import ImageGenerationRequest, ImageProviderError
        if kind not in {"product", "outfit"}:
            raise ValueError("unsupported draft visual kind")
        if kind == "outfit" and not reference_image:
            # Without the product image the outfit could show a different garment; never generate it from text alone.
            raise ImageProviderError("OUTFIT_REFERENCE_UNAVAILABLE")
        specification = json.dumps(product, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        companion = companion if kind == "outfit" else None
        companion_image = companion.get("image") if companion else None
        if kind == "product":
            instruction = (
                "Create a standalone new fashion product, studio product photograph. "
                "The JSON product specification below is the single source of truth. "
                "Use only its specified attributes; do not invent unspecified material, color, fit, or decoration. "
                "Show every listed design detail clearly.\n"
            )
        elif companion is None:
            instruction = (
                "Input image 1 is the product photograph of this new garment. Change only the presentation: show "
                "this exact garment worn by a model in a clean studio fashion photograph. Keep the garment identical "
                "to input image 1: the same color, pattern, silhouette, length, material and texture, construction, "
                "and every design detail. Do not redesign, recolor, add, remove, or substitute any detail, and do not "
                "add logos, text, or watermarks. The JSON product specification below describes the same garment.\n"
            )
        else:
            role = self._ROLE_PHRASES.get(companion.get("role") or "", "")
            stock_item = ("the exact existing stock item shown in input image 2" if companion_image
                          else "the existing stock item described in the STOCK ITEM JSON below")
            instruction = (
                "Input image 1 is the product photograph of this new garment."
                + (" Input image 2 is the photograph of an existing stock item." if companion_image else "")
                + f" Show one model in a clean studio fashion photograph wearing this exact new garment together "
                f"with {stock_item}{role}, styled as one outfit. Keep the new garment identical to input image 1: "
                "the same color, pattern, silhouette, length, material and texture, construction, and every design "
                "detail. "
                + ("Keep the stock item identical to input image 2 in the same way. " if companion_image
                   else "Render the stock item with exactly the listed category, color, material and fit. ")
                + "Do not redesign, recolor, add, remove, or substitute any detail of either item, do not hide either "
                "item, and do not add logos, text, or watermarks. The JSON product specification below describes the "
                "new garment.\n"
            )
        prompt = instruction + "PRODUCT SPECIFICATION (identical for product and outfit views):\n" + specification
        if companion is not None:
            prompt += ("\nSTOCK ITEM (" + ("input image 2" if companion_image else "no photograph") + "):\n"
                       + json.dumps(companion["specification"], sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")))
        request = ImageGenerationRequest(
            request_id=f"{request_id}:{kind}", season=product.get("season"), category=product.get("category"),
            prompt=prompt, prompt_version=self.prompt_version,
            prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(), evidence_ids=(),
            proposal_fields=(), limitations=(), conflicts=(), system_prompt=load_prompt("concept_image", "system"),
        )
        if kind == "product":
            return self._provider.generate(request).image_bytes
        extra_images = ((companion_image, companion["media_type"]),) if companion_image else ()
        return self._editor.edit(request, reference_image, extra_images=extra_images).image_bytes


class DraftArtifactStore:
    """Stores immutable bytes and binds every issuance to its originating request."""
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.images = self.root / "images"
        self.images.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "ownership.sqlite3"
        initialization_deadline = time.monotonic() + 10
        while True:
            try:
                with self._connect() as conn:
                    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                    if str(journal_mode).lower() != "wal":
                        conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("CREATE TABLE IF NOT EXISTS issued (request_id TEXT NOT NULL, kind TEXT NOT NULL, sha256 TEXT NOT NULL, uri TEXT NOT NULL, size_bytes INTEGER NOT NULL, PRIMARY KEY(request_id,kind))")
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).casefold() or time.monotonic() >= initialization_deadline:
                    raise
                time.sleep(0.05)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db, timeout=15)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def replay(self, request_id: str, source_sha256: str) -> dict | None:
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS workflow_response (request_id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, response_json TEXT NOT NULL)")
            row = conn.execute("SELECT source_sha256,response_json FROM workflow_response WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return None
        if row[0] != source_sha256:
            raise RequestReplayConflict("request_id was already used with a different source request")
        import json
        return json.loads(row[1])

    def save_response(self, request_id: str, source_sha256: str, response: dict) -> dict:
        serialized = json.dumps(response, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS workflow_response (request_id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, response_json TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS image_run (request_id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, status TEXT NOT NULL)")
            existing = conn.execute("SELECT source_sha256,response_json FROM workflow_response WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                if existing[0] != source_sha256:
                    raise RequestReplayConflict("request_id was already used with a different source request")
                # Concurrent identical requests may have different timing metadata.
                # Keep the first committed response as the idempotent result.
                return json.loads(existing[1])
            conn.execute("INSERT INTO workflow_response VALUES (?,?,?)", (request_id, source_sha256, serialized))
            conn.execute("UPDATE image_run SET status='complete' WHERE request_id=? AND source_sha256=?", (request_id, source_sha256))
        return response

    def claim_image_run(self, request_id: str, source_sha256: str) -> None:
        """Record paid image work before calling the provider; never silently repeat an uncertain run."""
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS image_run (request_id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, status TEXT NOT NULL)")
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT source_sha256,status FROM image_run WHERE request_id=?", (request_id,)).fetchone()
            if row:
                if row[0] != source_sha256:
                    raise RequestReplayConflict("request_id was already used with a different source request")
                raise ImageRunAlreadyClaimed("image generation for this request is already running or has an unknown outcome")
            conn.execute("INSERT INTO image_run VALUES (?,?,?)", (request_id, source_sha256, "started"))

    def put(self, request_id: str, kind: str, data: bytes, media_type: str = "image/png") -> dict:
        if not request_id or kind not in {"product", "outfit"} or media_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("invalid artifact metadata")
        if not data or len(data) > 10_000_000:
            raise ValueError("artifact size must be between 1 and 10000000 bytes")
        digest = hashlib.sha256(data).hexdigest()
        suffix = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[media_type]
        target = self.images / f"{digest}.{suffix}"
        if target.exists() and target.read_bytes() != data:
            raise ValueError("content-address collision")
        if not target.exists():
            target.write_bytes(data)
        uri = f"artifact://p06/images/{digest}.{suffix}"
        with self._connect() as conn:
            existing = conn.execute("SELECT sha256,uri,size_bytes FROM issued WHERE request_id=? AND kind=?", (request_id, kind)).fetchone()
            if existing and existing != (digest, uri, len(data)):
                raise ValueError("request already owns a different artifact for this visual")
            conn.execute("INSERT OR IGNORE INTO issued VALUES (?,?,?,?,?)", (request_id, kind, digest, uri, len(data)))
        return {"artifact_id": digest, "uri": uri, "sha256": digest, "media_type": media_type,
                "size_bytes": len(data), "immutable": True}

    def owns(self, request_id: str, kind: str, artifact: dict) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT sha256,uri,size_bytes FROM issued WHERE request_id=? AND kind=?", (request_id, kind)).fetchone()
        return row == (artifact.get("sha256"), artifact.get("uri"), artifact.get("size_bytes"))

    def resolve(self, request_id: str, kind: str, artifact: dict) -> Path:
        if not self.owns(request_id, kind, artifact):
            raise PermissionError("artifact is not owned by this request")
        name = Path(str(artifact.get("uri", "")).removeprefix("artifact://p06/images/")).name
        target = (self.images / name).resolve()
        if self.images not in target.parents or not target.is_file():
            raise FileNotFoundError("artifact unavailable")
        data = target.read_bytes()
        if len(data) != artifact["size_bytes"] or hashlib.sha256(data).hexdigest() != artifact["sha256"]:
            raise ValueError("artifact integrity check failed")
        return target
