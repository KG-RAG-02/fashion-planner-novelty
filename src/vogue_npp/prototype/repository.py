"""SQLite persistence for local briefs, image mockups, and review records."""

from __future__ import annotations

import html
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import IMAGEGEN_ASSET, IMAGEGEN_VARIANT_ID, database_path

BRIEF_FIELDS = {
    "title", "target_customer", "wearing_situation", "category_season", "price_range",
    "silhouette_fit", "material_function", "color_pattern", "differentiation",
    "feedback_application", "supply_constraints", "facts", "md_judgment", "assumptions",
}


class _ClosingConnection(sqlite3.Connection):
    """Make ``with connect()`` release file handles as well as its transaction."""

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool | None:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, factory=_ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize() -> None:
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS briefs (
                version INTEGER PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS variants (
                variant_id TEXT PRIMARY KEY, brief_version INTEGER NOT NULL,
                image_type TEXT NOT NULL, title TEXT NOT NULL, palette TEXT NOT NULL,
                prompt TEXT NOT NULL, model TEXT NOT NULL, created_at TEXT NOT NULL,
                svg TEXT NOT NULL, image_url TEXT NOT NULL DEFAULT '',
                image_source TEXT NOT NULL DEFAULT 'local_svg_mock',
                evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                prompt_version TEXT NOT NULL DEFAULT '', review_only INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS evaluations (
                evaluation_id TEXT PRIMARY KEY, variant_id TEXT NOT NULL,
                brief_version INTEGER NOT NULL, brand_fit INTEGER NOT NULL,
                customer_need INTEGER NOT NULL, differentiation INTEGER NOT NULL,
                price_feasibility INTEGER NOT NULL, production_feasibility INTEGER NOT NULL,
                adopted INTEGER NOT NULL, feedback TEXT NOT NULL, created_at TEXT NOT NULL
            );
        """)
        variant_columns = {row["name"] for row in db.execute("PRAGMA table_info(variants)").fetchall()}
        variant_migrations = {
            "image_url": "TEXT NOT NULL DEFAULT ''",
            "image_source": "TEXT NOT NULL DEFAULT 'local_svg_mock'",
            "evidence_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "prompt_version": "TEXT NOT NULL DEFAULT ''",
            "review_only": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, definition in variant_migrations.items():
            if column not in variant_columns:
                db.execute(f"ALTER TABLE variants ADD COLUMN {column} {definition}")
        version = db.execute("SELECT value FROM app_meta WHERE key='fixture_version'").fetchone()
        schema_version = "planning-brief-schema-1"
        if version is None or version["value"] != schema_version:
            db.execute("DELETE FROM app_meta WHERE key='fixture_version'")
            db.execute("INSERT INTO app_meta(key,value) VALUES('fixture_version',?)", (schema_version,))
        imagegen_variant = db.execute("SELECT 1 FROM variants WHERE variant_id=?", (IMAGEGEN_VARIANT_ID,)).fetchone()
        if imagegen_variant is None:
            prompt = (
                "Photorealistic premium fashion product concept photograph, a single young adult Korean female fashion model wearing a light utility anorak for a 27SS city-to-outdoors capsule. "
                "Full-body straight-on studio composition, neutral warm light-gray seamless background. Lightweight matte shell, relaxed slightly boxy fit, clean hood, half-zip front, functional angled zip pocket, adjustable hem. "
                "Muted light sage green with restrained dusty blue-gray color-block lower panel and sleeve detail; black relaxed technical trousers and neutral sneakers. "
                "Realistic fabric grain and natural drape, soft studio lighting, editorial e-commerce product photography. No logo, no text, no watermark, no extra props. Exploratory concept, not a production sample."
            )
            db.execute(
                "INSERT INTO variants(variant_id,brief_version,image_type,title,palette,prompt,model,created_at,svg) VALUES(?,?,?,?,?,?,?,?,?)",
                (IMAGEGEN_VARIANT_ID, 0, "lookbook", "Light sage utility anorak · ImageGen", "#B9C9A2",
                 prompt, "OpenAI ImageGen · 세부 모델 버전 미노출", "2026-11-05", ""),
            )


def _initial_brief() -> dict[str, Any]:
    return {
        "title": "상품기획 검토 초안",
        "target_customer": "미정",
        "wearing_situation": "미정",
        "category_season": "미정",
        "price_range": "미정",
        "silhouette_fit": "미정",
        "material_function": "미정",
        "color_pattern": "미정",
        "differentiation": "검토 필요",
        "feedback_application": "미제공",
        "supply_constraints": "미제공",
        "facts": "상품·트렌드와 전달된 입력의 근거를 확인한 뒤 작성",
        "md_judgment": "검토 전",
        "assumptions": "확정 사실과 가설을 구분해 입력",
        "evidence": [],
    }


def get_brief() -> dict[str, Any]:
    initialize()
    with connect() as db:
        row = db.execute("SELECT version,payload,created_at FROM briefs ORDER BY version DESC LIMIT 1").fetchone()
    if row:
        payload = json.loads(row["payload"])
        payload["evidence"] = _initial_brief()["evidence"]
        return {"version": row["version"], "created_at": row["created_at"], "payload": payload}
    return {"version": 0, "created_at": None, "payload": _initial_brief()}


def list_brief_versions() -> list[dict[str, Any]]:
    initialize()
    with connect() as db:
        rows = db.execute("SELECT version,payload,created_at FROM briefs ORDER BY version DESC").fetchall()
    return [{"version": row["version"], "payload": json.loads(row["payload"]), "created_at": row["created_at"]} for row in rows]


def save_brief(payload: dict[str, Any]) -> dict[str, Any]:
    initialize()
    clean = {key: str(payload.get(key, ""))[:4000] for key in BRIEF_FIELDS}
    if not clean["title"].strip():
        raise ValueError("브리프 제목을 입력해 주세요.")
    with connect() as db:
        version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM briefs").fetchone()[0]
        created_at = utc_now()
        db.execute("INSERT INTO briefs(version,payload,created_at) VALUES(?,?,?)", (version, json.dumps(clean, ensure_ascii=False), created_at))
    return {"version": version, "created_at": created_at, "payload": clean}


def generate_variant(payload: dict[str, Any], image_type: str, count: int) -> list[dict[str, Any]]:
    initialize()
    brief = get_brief()
    if image_type not in {"product", "lookbook"}:
        raise ValueError("이미지 유형은 product 또는 lookbook이어야 합니다.")
    count = min(max(int(count), 1), 4)
    palette = ["#B9C9A2", "#94A8B2", "#CFBBA1", "#84927D"]
    variants = []
    with connect() as db:
        for index in range(count):
            variant_id = "IMG-" + uuid.uuid4().hex[:10].upper()
            color = palette[index % len(palette)]
            title = ["Sage shell", "Dusty blue block", "Warm stone", "Field olive"][index % 4]
            created_at = utc_now()
            prompt = (
                f"MOCK ONLY · {image_type}; brief v{brief['version']}; {payload.get('title','')}; "
                f"silhouette={payload.get('silhouette_fit','')}; color={title}; "
                "visual draft only; material, fit, color accuracy, and manufacturability are unverified"
            )
            svg = _mock_svg(image_type, color, title, str(payload.get("title", "Concept")), index)
            db.execute(
                "INSERT INTO variants(variant_id,brief_version,image_type,title,palette,prompt,model,created_at,svg) VALUES(?,?,?,?,?,?,?,?,?)",
                (variant_id, brief["version"], image_type, title, color, prompt, "Local SVG Mock v1", created_at, svg),
            )
            variants.append({
                "variant_id": variant_id, "brief_version": brief["version"], "image_type": image_type,
                "title": title, "palette": color, "prompt": prompt, "model": "Local SVG Mock v1",
                "created_at": created_at, "image_url": f"/api/variants/{variant_id}.svg",
            })
    return variants


def save_generated_image_variant(
    *,
    variant_id: str,
    image_type: str,
    title: str,
    image_url: str,
    prompt: str,
    model: str,
    evidence_ids: list[str],
    prompt_version: str,
    review_only: bool = True,
) -> dict[str, Any]:
    """Persist a real generated image in the same reviewable variant list."""
    initialize()
    clean_id = str(variant_id).strip()[:80]
    clean_url = str(image_url).strip()[:300]
    if not clean_id or not clean_url.startswith("/api/generated-images/"):
        raise ValueError("실제 생성 시안 식별자 또는 이미지 경로가 올바르지 않습니다.")
    brief_version = get_brief()["version"]
    created_at = utc_now()
    clean_evidence = list(dict.fromkeys(str(value)[:200] for value in evidence_ids if value))[:100]
    clean_prompt = str(prompt)[:30000]
    clean_title = str(title).strip()[:200]
    clean_model = str(model).strip()[:120]
    clean_prompt_version = str(prompt_version).strip()[:120]
    with connect() as db:
        db.execute(
            """INSERT OR REPLACE INTO variants
               (variant_id,brief_version,image_type,title,palette,prompt,model,created_at,svg,
                image_url,image_source,evidence_ids_json,prompt_version,review_only)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (clean_id, brief_version, image_type, clean_title, "", clean_prompt, clean_model,
             created_at, "", clean_url, "model_generated",
             json.dumps(clean_evidence, ensure_ascii=False), clean_prompt_version, int(review_only)),
        )
    return {
        "variant_id": clean_id, "brief_version": brief_version, "image_type": image_type,
        "title": clean_title, "palette": "", "prompt": clean_prompt, "model": clean_model,
        "created_at": created_at, "image_url": clean_url, "image_source": "model_generated",
        "evidence_ids": clean_evidence, "prompt_version": clean_prompt_version,
        "review_only": review_only,
    }


def _mock_svg(image_type: str, color: str, title: str, brief_title: str, variant_index: int) -> str:
    color_block = variant_index % 2 == 1
    safe_title = html.escape(title)
    safe_brief = html.escape(brief_title)
    if image_type == "product":
        garment = f'''<path d="M230 183 L280 134 Q300 122 320 139 L344 160 L371 139 Q390 123 411 136 L461 184 L428 218 L407 200 L407 433 Q345 458 282 433 L282 200 L260 218 Z" fill="{color}" stroke="#34423b" stroke-width="4"/>
        <path d="M281 177 Q345 105 407 177 L393 216 Q345 187 295 216 Z" fill="#30453b" stroke="#34423b" stroke-width="4"/>
        <path d="M345 191 L345 432" stroke="#34423b" stroke-width="5"/>
        <path d="M302 292 L334 292 L334 331 L302 331 Z M356 292 L388 292 L388 331 L356 331 Z" fill="none" stroke="#34423b" stroke-width="3"/>
        <path d="M304 335 L332 335 M358 335 L386 335" stroke="#34423b" stroke-width="3"/>'''
    else:
        garment = f'''<circle cx="345" cy="126" r="35" fill="#d9c6ad"/>
        <path d="M310 168 Q345 150 380 168 L416 238 L393 254 L378 218 L392 352 L365 355 L345 274 L326 355 L298 352 L313 218 L296 254 L273 238 Z" fill="{color}" stroke="#34423b" stroke-width="4"/>
        <path d="M310 183 Q345 144 380 183 L370 212 Q345 193 320 212 Z" fill="#30453b"/>
        <path d="M330 350 L326 468 L302 518 L339 518 L351 397 L365 518 L402 518 L374 468 L365 350 Z" fill="#343c3a"/>'''
    block = f'<path d="M345 190 L345 432 L407 420 L407 200 Z" fill="#435b68" opacity=".88"/>' if color_block and image_type == "product" else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 690 590" role="img" aria-label="Mock fashion concept illustration">
      <rect width="690" height="590" rx="24" fill="#f2f0e9"/><circle cx="345" cy="280" r="205" fill="#e6e9df"/>
      <path d="M72 470 H618" stroke="#c6cbc0" stroke-width="2"/><ellipse cx="345" cy="468" rx="92" ry="13" fill="#d1d4cc"/>
      {garment}{block}
      <rect x="38" y="34" width="614" height="54" rx="13" fill="#fff" opacity=".9"/>
      <text x="58" y="67" font-family="Arial,sans-serif" font-size="17" font-weight="700" fill="#26382f">MOCK CONCEPT · {safe_title.upper()}</text>
      <text x="40" y="552" font-family="Arial,sans-serif" font-size="17" fill="#42534a">{safe_brief}</text>
      <text x="652" y="552" text-anchor="end" font-family="Arial,sans-serif" font-size="12" fill="#66746c">NOT A PRODUCT SAMPLE</text>
    </svg>'''


def get_variant_image(variant_id: str) -> str | None:
    initialize()
    with connect() as db:
        row = db.execute("SELECT svg FROM variants WHERE variant_id=?", (variant_id,)).fetchone()
    return (row["svg"] or None) if row else None


def list_variants() -> list[dict[str, Any]]:
    initialize()
    with connect() as db:
        rows = db.execute(
            "SELECT variant_id,brief_version,image_type,title,palette,prompt,model,created_at,image_url,image_source,evidence_ids_json,prompt_version,review_only FROM variants "
            "ORDER BY CASE WHEN image_source='model_generated' AND variant_id<>? THEN 0 WHEN variant_id=? THEN 1 ELSE 2 END, created_at DESC",
            (IMAGEGEN_VARIANT_ID, IMAGEGEN_VARIANT_ID),
        ).fetchall()
    variants = []
    for row in rows:
        item = dict(row)
        item["image_url"] = (
            item["image_url"] or
            (IMAGEGEN_ASSET if row["variant_id"] == IMAGEGEN_VARIANT_ID else f"/api/variants/{row['variant_id']}.svg")
        )
        if row["variant_id"] == IMAGEGEN_VARIANT_ID:
            item["image_source"] = "model_generated"
        item["evidence_ids"] = json.loads(item.pop("evidence_ids_json") or "[]")
        item["review_only"] = bool(item["review_only"])
        variants.append(item)
    return variants


def save_evaluation(payload: dict[str, Any]) -> dict[str, Any]:
    initialize()
    variant_id = str(payload.get("variant_id", ""))
    ratings = {}
    for key in ("brand_fit", "customer_need", "differentiation", "price_feasibility", "production_feasibility"):
        value = int(payload.get(key, 0))
        if value < 1 or value > 5:
            raise ValueError("모든 평가 항목은 1–5점으로 입력해 주세요.")
        ratings[key] = value
    adopted = payload.get("adopted", False)
    if not isinstance(adopted, bool):
        raise ValueError("채택 후보 여부는 true 또는 false로 입력해 주세요.")
    feedback = str(payload.get("feedback", ""))[:4000]
    evaluation_id = "REV-" + uuid.uuid4().hex[:10].upper()
    with connect() as db:
        variant = db.execute("SELECT brief_version FROM variants WHERE variant_id=?", (variant_id,)).fetchone()
        if variant is None:
            raise ValueError("시안을 찾을 수 없습니다.")
        created_at = utc_now()
        db.execute(
            "INSERT INTO evaluations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (evaluation_id, variant_id, variant["brief_version"], ratings["brand_fit"], ratings["customer_need"],
             ratings["differentiation"], ratings["price_feasibility"], ratings["production_feasibility"],
             int(adopted), feedback, created_at),
        )
    return {"evaluation_id": evaluation_id, "variant_id": variant_id, "created_at": created_at}


def list_evaluations() -> list[dict[str, Any]]:
    initialize()
    with connect() as db:
        rows = db.execute("""
                SELECT e.*,v.title AS variant_title,v.image_type,
                    COALESCE(NULLIF(v.image_url,''), '/api/variants/' || v.variant_id || '.svg') AS image_url
            FROM evaluations e LEFT JOIN (
                SELECT variant_id,title,image_type,'/api/variants/' || variant_id || '.svg' AS image_url FROM variants
            ) v USING(variant_id)
            ORDER BY e.created_at DESC
        """).fetchall()
    results = [dict(row) for row in rows]
    for item in results:
        if item["variant_id"] == IMAGEGEN_VARIANT_ID:
            item["image_url"] = IMAGEGEN_ASSET
    return results
