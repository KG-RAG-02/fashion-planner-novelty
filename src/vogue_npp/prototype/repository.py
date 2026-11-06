"""SQLite persistence for local briefs, image mockups, and review records."""

from __future__ import annotations

import html
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .analytics import analyze
from .config import IMAGEGEN_ASSET, IMAGEGEN_VARIANT_ID, database_path
from .fixtures import load_fixture

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
            CREATE TABLE IF NOT EXISTS hm_planning_reviews (
                review_id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL,
                request_payload TEXT NOT NULL, decision_payload TEXT NOT NULL,
                analysis_version TEXT NOT NULL, source_period TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hm_planning_briefs (
                brief_id TEXT PRIMARY KEY, brief_version INTEGER NOT NULL,
                opportunity_id TEXT NOT NULL, payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(opportunity_id, brief_version)
            );
            CREATE TABLE IF NOT EXISTS hm_brief_reviews (
                review_id TEXT PRIMARY KEY, brief_id TEXT NOT NULL,
                brief_version INTEGER NOT NULL, decision TEXT NOT NULL,
                ratings_json TEXT NOT NULL, feedback TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(brief_id) REFERENCES hm_planning_briefs(brief_id)
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
        fixture = load_fixture()
        if version is None or version["value"] != fixture["schema_version"]:
            db.execute("DELETE FROM app_meta WHERE key='fixture_version'")
            db.execute("INSERT INTO app_meta(key,value) VALUES('fixture_version',?)", (fixture["schema_version"],))
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


def _initial_brief(analysis: dict[str, Any]) -> dict[str, Any]:
    opportunity = next((item for item in analysis["opportunities"] if item["kind"] == "고객 의견 신호"), None)
    best = max(analysis["products"], key=lambda row: row["units"])
    return {
        "title": "Light Utility Anorak · 27SS",
        "target_customer": "도시 이동과 짧은 야외 활동을 함께 하는 고객 (가설)",
        "wearing_situation": "출퇴근, 주말 산책, 가벼운 야외 활동 (검토 가설)",
        "category_season": "Light Outerwear · 27SS",
        "price_range": "₩79,900–₩129,900 (가상 26SS 표본 가격 범위; 목표가 미정)",
        "silhouette_fit": "가벼운 후드형 유틸리티 아우터 · 여유핏 검토",
        "material_function": "소재 미정 · 발수·통기·구김 회복 시험 필요",
        "color_pattern": "라이트 세이지 또는 먼지 낀 블루 탐색 (가설)",
        "differentiation": "기존 경량 아우터의 휴대성을 참고하면서 구김 및 통기성 불편을 개선하는 방향 검토",
        "feedback_application": opportunity["summary"] if opportunity else "고객 피드백 표본 확인 필요",
        "supply_constraints": "가상 리드타임 스냅샷은 표에 표시됩니다. 공급업체 견적·MOQ·생산능력 자료는 없으므로 실제 원가와 생산 가능성을 확인해야 합니다.",
        "facts": f"가상 상품 표본에서 {best['name']}이 12주 {best['units']:,} units로 가장 많이 관측됨. 실제 브랜드/수요 사실이 아님.",
        "md_judgment": "가벼운 유틸리티 아우터에서 활동성과 관리 편의를 함께 강조할 가치가 있는지 검토한다.",
        "assumptions": "타깃 고객과 사용 상황은 확인된 고객 세그먼트가 아니라 MD 검토 가설이다.",
        "evidence": [ev for item in analysis["opportunities"] for ev in item["evidence"]],
    }


def get_brief() -> dict[str, Any]:
    initialize()
    analysis = analyze()
    with connect() as db:
        row = db.execute("SELECT version,payload,created_at FROM briefs ORDER BY version DESC LIMIT 1").fetchone()
    if row:
        payload = json.loads(row["payload"])
        payload["evidence"] = _initial_brief(analysis)["evidence"]
        return {"version": row["version"], "created_at": row["created_at"], "payload": payload}
    return {"version": 0, "created_at": None, "payload": _initial_brief(analysis)}


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


def save_hm_planning_review(payload: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """Persist an actual-H&M planning decision separately from synthetic briefs."""
    initialize()
    opportunity_id = str(payload.get("opportunity_id", "")).strip()
    opportunity = next((row for row in analysis.get("opportunity_candidates", []) if row.get("opportunity_id") == opportunity_id), None)
    if opportunity is None:
        raise ValueError("선택한 기획 후보를 현재 분석 결과에서 찾을 수 없습니다.")
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    reason = str(decision.get("selection_reason", "")).strip()
    if not reason:
        raise ValueError("후보 선택 근거를 입력해 주세요.")
    clean_request = {
        "target_season": str(request.get("target_season", "")).strip()[:100] or None,
        "market": str(request.get("market", "")).strip()[:200] or None,
        "channel": str(request.get("channel", "")).strip()[:100] or None,
        "product_group_name": opportunity["category"]["product_group_name"],
        "product_type_name": opportunity["category"]["product_type_name"],
        "price_hypothesis": str(request.get("price_hypothesis", "")).strip()[:300] or None,
        "design_constraints": str(request.get("design_constraints", "")).strip()[:1000] or None,
        "missing_fields": ["trend_evidence", "inventory_and_returns", "cost_and_margin", "customer_segments"],
    }
    clean_decision = {
        "selection_reason": reason[:2000],
        "counter_evidence": str(decision.get("counter_evidence", "")).strip()[:2000] or None,
        "unknowns_to_validate": str(decision.get("unknowns_to_validate", "")).strip()[:2000] or None,
        "opportunity_snapshot": opportunity,
    }
    review_id = "HM-REVIEW-" + uuid.uuid4().hex[:12].upper()
    created_at = utc_now()
    period = analysis.get("observation_period", {})
    source_period = f"{period.get('start', '')}–{period.get('end', '')}"
    with connect() as db:
        db.execute("INSERT INTO hm_planning_reviews VALUES(?,?,?,?,?,?,?)", (
            review_id, opportunity_id, json.dumps(clean_request, ensure_ascii=False),
            json.dumps(clean_decision, ensure_ascii=False), str(analysis.get("analysis_version", "unknown")),
            source_period, created_at,
        ))
    return {"review_id": review_id, "opportunity_id": opportunity_id, "request": clean_request,
            "decision": clean_decision, "analysis_version": analysis.get("analysis_version"),
            "source_period": source_period, "created_at": created_at}


def list_hm_planning_reviews() -> list[dict[str, Any]]:
    """List actual-data planning reviews, separate from synthetic brief records."""
    initialize()
    with connect() as db:
        rows = db.execute("SELECT * FROM hm_planning_reviews ORDER BY created_at DESC LIMIT 100").fetchall()
    return [{"review_id": row["review_id"], "opportunity_id": row["opportunity_id"],
             "request": json.loads(row["request_payload"]), "decision": json.loads(row["decision_payload"]),
             "analysis_version": row["analysis_version"], "source_period": row["source_period"],
             "created_at": row["created_at"]} for row in rows]


def save_hm_planning_brief(payload: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """Build and version a deterministic brief from one H&M candidate."""
    initialize()
    from ..workflows.planning import build_review_brief

    brief = build_review_brief(payload, analysis)
    brief_id = "HM-BRIEF-" + uuid.uuid4().hex[:12].upper()
    opportunity_id = brief["opportunity_id"]
    with connect() as db:
        version = int(db.execute("SELECT COALESCE(MAX(brief_version),0)+1 FROM hm_planning_briefs WHERE opportunity_id=?", (opportunity_id,)).fetchone()[0])
        created_at = utc_now()
        brief["brief_id"] = brief_id
        brief["brief_version"] = version
        brief["created_at"] = created_at
        brief["image_prompt_package"]["brief_id"] = brief_id
        db.execute("INSERT INTO hm_planning_briefs VALUES(?,?,?,?,?)", (brief_id, version, opportunity_id, json.dumps(brief, ensure_ascii=False), created_at))
    return brief


def list_hm_planning_briefs() -> list[dict[str, Any]]:
    initialize()
    with connect() as db:
        rows = db.execute("SELECT payload FROM hm_planning_briefs ORDER BY created_at DESC LIMIT 100").fetchall()
    return [json.loads(row["payload"]) for row in rows]


def save_hm_brief_review(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a human review against an immutable H&M brief version."""
    initialize()
    brief_id = str(payload.get("brief_id", "")).strip()
    decision = str(payload.get("decision", "")).strip()
    if decision not in {"revise", "advance", "hold"}:
        raise ValueError("검토 결정을 선택해 주세요.")
    supplied_ratings = payload.get("ratings") if isinstance(payload.get("ratings"), dict) else {}
    ratings: dict[str, int] = {}
    for key in ("evidence_grounding", "request_fit", "product_direction"):
        try:
            value = int(supplied_ratings.get(key, 0))
        except (TypeError, ValueError):
            value = 0
        if not 1 <= value <= 5:
            raise ValueError("모든 검토 항목은 1–5점으로 입력해 주세요.")
        ratings[key] = value
    feedback = str(payload.get("feedback", "")).strip()[:4000]
    review_id = "HM-BRIEF-REVIEW-" + uuid.uuid4().hex[:10].upper()
    created_at = utc_now()
    with connect() as db:
        brief = db.execute("SELECT brief_version FROM hm_planning_briefs WHERE brief_id=?", (brief_id,)).fetchone()
        if brief is None:
            raise ValueError("검토할 브리프를 찾을 수 없습니다.")
        db.execute("INSERT INTO hm_brief_reviews VALUES(?,?,?,?,?,?,?)", (
            review_id, brief_id, brief["brief_version"], decision,
            json.dumps(ratings, ensure_ascii=False), feedback, created_at,
        ))
    return {"review_id": review_id, "brief_id": brief_id, "brief_version": brief["brief_version"],
            "decision": decision, "ratings": ratings, "feedback": feedback, "created_at": created_at}


def list_hm_brief_reviews() -> list[dict[str, Any]]:
    initialize()
    with connect() as db:
        rows = db.execute("SELECT * FROM hm_brief_reviews ORDER BY created_at DESC LIMIT 200").fetchall()
    return [{"review_id": row["review_id"], "brief_id": row["brief_id"],
             "brief_version": row["brief_version"], "decision": row["decision"],
             "ratings": json.loads(row["ratings_json"]), "feedback": row["feedback"],
             "created_at": row["created_at"]} for row in rows]
