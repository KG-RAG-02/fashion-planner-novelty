"""Synthetic-data analytics, lexical document retrieval, and local review storage."""

from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "examples" / "fixtures" / "prototype_demo.json"
DB_PATH = Path(os.getenv("VOGUE_DB_PATH", str(ROOT / "data" / "local" / "prototype.sqlite3")))
HM_ANALYSIS_PATH = Path(os.getenv(
    "VOGUE_HM_ANALYSIS_PATH",
    str(ROOT / "data" / "processed" / "hm-personalized-fashion-recommendations" / "hm_analysis.json"),
))
IMAGEGEN_VARIANT_ID = "IMG-27SS-IMAGEGEN-01"
IMAGEGEN_ASSET = "/assets/27ss-light-utility-anorak-imagegen.png"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_fixture() -> dict[str, Any]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_ids = {source["source_id"] for source in data["sources"]}
    for key in ("products", "sales_profiles", "inventory", "feedback", "documents"):
        for row in data[key]:
            if row["source_id"] not in source_ids:
                raise ValueError(f"Fixture row has unknown source: {row['source_id']}")
    return data


def get_hm_analysis() -> dict[str, Any] | None:
    """Return the separate real Kaggle analysis report when the pipeline ran."""
    if not HM_ANALYSIS_PATH.is_file():
        return None
    return json.loads(HM_ANALYSIS_PATH.read_text(encoding="utf-8"))


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
                svg TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evaluations (
                evaluation_id TEXT PRIMARY KEY, variant_id TEXT NOT NULL,
                brief_version INTEGER NOT NULL, brand_fit INTEGER NOT NULL,
                customer_need INTEGER NOT NULL, differentiation INTEGER NOT NULL,
                price_feasibility INTEGER NOT NULL, production_feasibility INTEGER NOT NULL,
                adopted INTEGER NOT NULL, feedback TEXT NOT NULL, created_at TEXT NOT NULL
            );
        """)
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


def _source_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["source_id"]: row for row in data["sources"]}


def _period_sales(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    products = {product["style_id"]: product for product in data["products"]}
    result: dict[str, dict[str, Any]] = {}
    for profile in data["sales_profiles"]:
        product = products[profile["style_id"]]
        units = sum(profile["weekly_units"])
        list_price = product["price_krw"]
        discount_rate = profile["discount_rate"]
        revenue = round(units * list_price * (1 - discount_rate))
        result[profile["style_id"]] = {
            "units": units,
            "revenue_krw": revenue,
            "discount_rate": discount_rate,
            "weekly_average": units / len(profile["weekly_units"]),
            "return_units": profile["return_units"],
            "return_rate": profile["return_units"] / units if units else 0,
            "stockout_days": profile["stockout_days"],
            "channel": profile["channel"],
            "source_id": profile["source_id"],
            "week_count": len(profile["weekly_units"]),
        }
    return result


def analyze() -> dict[str, Any]:
    """Calculate fixture metrics deterministically; never ask a model to do arithmetic."""
    data = load_fixture()
    sources = _source_map(data)
    sales = _period_sales(data)
    inventory = {row["style_id"]: row for row in data["inventory"]}
    products = {row["style_id"]: row for row in data["products"]}
    week_starts = [
        week
        for profile in data["sales_profiles"]
        for week in _weeks_for_profile(profile)
    ]
    start = min(week_starts)
    end = (date.fromisoformat(max(week_starts)) + timedelta(days=6)).isoformat()
    total_units = sum(item["units"] for item in sales.values())
    total_revenue = sum(item["revenue_krw"] for item in sales.values())

    best = max(sales, key=lambda style: sales[style]["units"])
    best_product = products[best]
    best_sales = sales[best]
    opportunities: list[dict[str, Any]] = [{
        "kind": "성과 신호",
        "title": f"판매 수량 상위: {best_product['name']}",
        "summary": f"{best_sales['units']:,} units가 관측됐습니다. {best_product['color']} 색상, {best_product['fit']} 핏 상품입니다.",
        "value": f"{best_sales['units']:,} units",
        "period": f"{start}–{end} · {best_sales['week_count']}주",
        "evidence": [
            _evidence(best_sales["source_id"], f"{best}:units", sources, "12주 구매 수량 합계"),
            _evidence(best_product["source_id"], f"{best}:catalog", sources, "상품 속성"),
        ],
        "caveat": "가상 데이터의 관측 결과이며 다음 시즌 판매 예측이 아닙니다.",
    }]

    stock_rows = []
    for style_id, stock in inventory.items():
        metric = sales.get(style_id)
        if not metric:
            continue
        cover = stock["on_hand_units"] / metric["weekly_average"] if metric["weekly_average"] else None
        stock_rows.append((style_id, stock, metric, cover))
    low_cover = min((row for row in stock_rows if row[3] is not None), key=lambda row: row[3])
    _, low_stock, low_metric, low_cover_weeks = low_cover
    low_product = products[low_cover[0]]
    opportunities.append({
        "kind": "재고 검토 신호",
        "title": f"재고 커버가 짧은 편: {low_product['name']}",
        "summary": f"현재고 {low_stock['on_hand_units']:,} units ÷ 12주 평균 주간 판매 {low_metric['weekly_average']:.1f} units = {low_cover_weeks:.1f}주.",
        "value": f"{low_cover_weeks:.1f}주 커버",
        "period": f"재고 기준일 {sources[low_stock['source_id']]['as_of']} · 판매 {start}–{end}",
        "evidence": [
            _evidence(low_stock["source_id"], f"{low_cover[0]}:inventory", sources, "현재고 스냅샷"),
            _evidence(low_metric["source_id"], f"{low_cover[0]}:weekly-average", sources, "12주 평균 판매"),
            _evidence("SRC-DEMO-KPI-01", "DOC-KPI-01-P3", sources, "커버 주수 정의"),
        ],
        "caveat": "가상 재고 스냅샷 기준의 검토 신호입니다. 입고 예정·품절 이력·발주 판단을 대체하지 않습니다.",
    })
    high_cover = max((row for row in stock_rows if row[3] is not None), key=lambda row: row[3])
    _, high_stock, high_metric, high_cover_weeks = high_cover
    high_product = products[high_cover[0]]
    if high_cover_weeks >= 12:
        opportunities.append({
            "kind": "재고 검토 신호",
            "title": f"재고 커버가 긴 편: {high_product['name']}",
            "summary": f"현재고 {high_stock['on_hand_units']:,} units ÷ 12주 평균 주간 판매 {high_metric['weekly_average']:.1f} units = {high_cover_weeks:.1f}주.",
            "value": f"{high_cover_weeks:.1f}주 커버",
            "period": f"재고 기준일 {sources[high_stock['source_id']]['as_of']} · 판매 {start}–{end}",
            "evidence": [
                _evidence(high_stock["source_id"], f"{high_cover[0]}:inventory", sources, "현재고 스냅샷"),
                _evidence(high_metric["source_id"], f"{high_cover[0]}:weekly-average", sources, "12주 평균 판매"),
                _evidence("SRC-DEMO-KPI-01", "DOC-KPI-01-P3", sources, "커버 주수 정의"),
            ],
            "caveat": "가상 데이터에서 비교적 긴 커버로 표시한 검토 신호입니다. 과잉 재고나 할인 필요를 자동 판정하지 않습니다.",
        })

    feedback_counts: dict[str, list[dict[str, Any]]] = {}
    for row in data["feedback"]:
        if row["rating"] <= 3:
            feedback_counts.setdefault(row["theme"], []).append(row)
    repeated = max(feedback_counts.items(), key=lambda item: len(item[1]))
    theme, feedback_rows = repeated
    themed_product = products[feedback_rows[0]["style_id"]]
    opportunities.append({
        "kind": "고객 의견 신호",
        "title": f"반복 언급된 불만 주제: {theme}",
        "summary": f"낮은 평점(1–3점) {len(feedback_rows)}건에서 같은 주제가 나타났습니다. 예: “{feedback_rows[0]['text']}”",
        "value": f"{len(feedback_rows)}건",
        "period": "2026-01–2026-02 · 가상 리뷰 표본",
        "evidence": [
            _evidence(row["source_id"], row["feedback_id"], sources, f"고객 의견 · {row['date']} · {row['rating']}/5")
            for row in feedback_rows
        ],
        "caveat": f"가상 리뷰 표본이며 대표성 있는 고객 조사로 간주할 수 없습니다. 연결 상품: {themed_product['name']}.",
    })

    present_values = {
        "color": {product["color"].casefold() for product in data["products"]},
        "material": {product["material"].casefold() for product in data["products"]},
        "fit": {product["fit"].casefold() for product in data["products"]},
    }
    for check in data["scope"].get("assortment_checks", []):
        absent = [value for value in check["values"] if value.casefold() not in present_values.get(check["field"], set())]
        if absent and data["scope"].get("catalog_scope_complete"):
            opportunities.append({
                "kind": "구색 검토 가설",
                "title": f"트렌드 검토 {check['field']} 표본 구색에서 미확인: {', '.join(absent)}",
                "summary": f"완전성이 설정된 가상 {data['scope']['category']} 표본 {len(data['products'])}개 Style에서 해당 값이 확인되지 않았습니다.",
                "value": f"{len(absent)}개 값 미포함",
                "period": "상품 기준 26SS 가상 구색 · 트렌드 참고 27SS",
                "evidence": [
                    _evidence(data["scope"]["source_id"], "catalog:scope", sources, "표본 카탈로그 범위"),
                    _evidence(check["source_id"], check["passage_id"], sources, "27SS 색상 탐색 방향"),
                ],
                "caveat": "신규 색상 기회가 확정된 것은 아닙니다. MD가 시즌 적합성·소재/염색 가능성을 검토해야 합니다.",
            })

    table = []
    for style_id, product in products.items():
        metric = sales[style_id]
        stock = inventory[style_id]
        cover = stock["on_hand_units"] / metric["weekly_average"] if metric["weekly_average"] else 0
        table.append({
            **product,
            "units": metric["units"], "revenue_krw": metric["revenue_krw"],
            "discount_rate": metric["discount_rate"], "return_rate": metric["return_rate"],
            "stockout_days": metric["stockout_days"], "channel": metric["channel"],
            "on_hand_units": stock["on_hand_units"], "inbound_units": stock["inbound_units"],
            "lead_time_days": stock["lead_time_days"],
            "cover_weeks": round(cover, 1),
            "evidence": [
                _evidence(metric["source_id"], f"{style_id}:sales", sources, "12주 판매 aggregate"),
                _evidence(stock["source_id"], f"{style_id}:inventory", sources, "현재고 스냅샷"),
                _evidence(product["source_id"], f"{style_id}:catalog", sources, "상품 속성"),
            ],
        })

    total_stockout_days = sum(metric["stockout_days"] for metric in sales.values())
    return {
        "scope": data["scope"],
        "period": {"start": start, "end": end, "weeks": 12},
        "kpis": [
            {"label": "관측 판매 수량", "value": f"{total_units:,}", "unit": "units", "source_ids": ["SRC-DEMO-SALES-01"], "record_id": "sales:category", "period": f"{start}–{end}"},
            {"label": "계산 매출 참고값", "value": f"₩{total_revenue:,.0f}", "unit": "KRW (synthetic estimate)", "source_ids": ["SRC-DEMO-SALES-01", "SRC-DEMO-CATALOG-01"], "record_id": "sales:category", "period": f"{start}–{end}"},
            {"label": "가중 평균 할인율", "value": f"{sum(x['discount_rate'] * x['units'] for x in sales.values()) / total_units:.1%}", "unit": "sales-weighted ratio", "source_ids": ["SRC-DEMO-SALES-01"], "record_id": "sales:category", "period": f"{start}–{end}"},
            {"label": "판매 기록된 품절 일수", "value": str(total_stockout_days), "unit": "style-days (sample field)", "source_ids": ["SRC-DEMO-SALES-01"], "record_id": "sales:category", "period": f"{start}–{end}"},
        ],
        "opportunities": opportunities,
        "products": table,
        "sources": list(sources.values()),
        "feedback": data["feedback"],
        "documents": data["documents"],
        "fixture_notice": "모든 상품·판매·재고·고객 의견·문서는 합성 시연 자료입니다. 실제 회사 데이터와 혼합하지 마세요.",
        "analysis_notes": [
            "매출 참고값은 합성 MSRP × (1 − 합성 할인율) × units 계산입니다. 원천 매출이 아닙니다.",
            "반품률은 합성 return units ÷ 합성 판매 units이며 실제 KPI 정의가 아닙니다.",
            "재고 커버는 현재고 ÷ 12주 평균 판매로 계산한 탐색용 값입니다.",
            "판매 집계의 채널은 합성 데이터의 표시명이며 실제 채널 코드 체계가 아닙니다.",
        ],
    }


def _weeks_for_profile(profile: dict[str, Any]) -> list[str]:
    from datetime import date, timedelta

    start = date(2025, 12, 1)
    return [(start + timedelta(days=7 * index)).isoformat() for index in range(len(profile["weekly_units"]))]


def _evidence(source_id: str, record_id: str, sources: dict[str, dict[str, Any]], label: str) -> dict[str, Any]:
    source = sources[source_id]
    return {
        "label": label,
        "record_id": record_id,
        "source_id": source_id,
        "source_name": source["name"],
        "period": source["period"],
        "version": source["version"],
        "permission": source["permission"],
        "as_of": source["as_of"],
    }


def search_documents(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    data = load_fixture()
    sources = _source_map(data)
    tokens = [token.casefold() for token in re.findall(r"[\w가-힣]+", query) if len(token) > 1]
    if not tokens:
        return []
    results = []
    for document in data["documents"]:
        for passage in document["passages"]:
            haystack = f"{document['title']} {passage['section']} {passage['text']}".casefold()
            score = sum(haystack.count(token) for token in set(tokens))
            if score:
                results.append({
                    "score": score,
                    "title": document["title"], "section": passage["section"],
                    "text": passage["text"], "passage_id": passage["passage_id"],
                    "source": _evidence(document["source_id"], passage["passage_id"], sources, "문서 구절"),
                    "document_version": document["version"],
                    "season": document["season"],
                })
    return sorted(results, key=lambda item: (-item["score"], item["passage_id"]))[:limit]


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


BRIEF_FIELDS = {
    "title", "target_customer", "wearing_situation", "category_season", "price_range",
    "silhouette_fit", "material_function", "color_pattern", "differentiation",
    "feedback_application", "supply_constraints", "facts", "md_judgment", "assumptions",
}


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
            prompt = (
                f"MOCK ONLY · {image_type}; brief v{brief['version']}; {payload.get('title','')}; "
                f"silhouette={payload.get('silhouette_fit','')}; color={title}; "
                "visual draft only; material, fit, color accuracy, and manufacturability are unverified"
            )
            svg = _mock_svg(image_type, color, title, str(payload.get("title", "Concept")), index)
            db.execute(
                "INSERT INTO variants VALUES(?,?,?,?,?,?,?,?,?)",
                (variant_id, brief["version"], image_type, title, color, prompt, "Local SVG Mock v1", utc_now(), svg),
            )
            variants.append({
                "variant_id": variant_id, "brief_version": brief["version"], "image_type": image_type,
                "title": title, "palette": color, "prompt": prompt, "model": "Local SVG Mock v1",
                "created_at": utc_now(), "image_url": f"/api/variants/{variant_id}.svg",
            })
    return variants


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
            "SELECT variant_id,brief_version,image_type,title,palette,prompt,model,created_at FROM variants "
            "ORDER BY CASE WHEN variant_id=? THEN 0 ELSE 1 END, created_at DESC",
            (IMAGEGEN_VARIANT_ID,),
        ).fetchall()
    return [{
        **dict(row),
        "image_url": IMAGEGEN_ASSET if row["variant_id"] == IMAGEGEN_VARIANT_ID else f"/api/variants/{row['variant_id']}.svg",
        "image_source": "model_generated" if row["variant_id"] == IMAGEGEN_VARIANT_ID else "local_svg_mock",
    } for row in rows]


def save_evaluation(payload: dict[str, Any]) -> dict[str, Any]:
    initialize()
    variant_id = str(payload.get("variant_id", ""))
    ratings = {}
    for key in ("brand_fit", "customer_need", "differentiation", "price_feasibility", "production_feasibility"):
        value = int(payload.get(key, 0))
        if value < 1 or value > 5:
            raise ValueError("모든 평가 항목은 1–5점으로 입력해 주세요.")
        ratings[key] = value
    adopted = bool(payload.get("adopted", False))
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
            SELECT e.*,v.title AS variant_title,v.image_type,v.image_url
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


def get_evidence(record_id: str) -> dict[str, Any] | None:
    """Resolve a displayed evidence ID to the corresponding synthetic record."""
    data = load_fixture()
    sources = _source_map(data)
    related_source_ids: list[str] = []
    if record_id == "catalog:scope":
        row: Any = {"scope": data["scope"], "style_count": len(data["products"]), "styles": [p["style_id"] for p in data["products"]]}
        source_id = data["scope"]["source_id"]
        kind = "catalog_scope"
    elif record_id.startswith("DOC-"):
        found = next(((doc, passage) for doc in data["documents"] for passage in doc["passages"] if passage["passage_id"] == record_id), None)
        if not found:
            return None
        doc, passage = found
        row = {"document": doc["title"], "section": passage["section"], "text": passage["text"], "date": doc["date"], "season": doc["season"], "version": doc["version"]}
        source_id = doc["source_id"]
        kind = "document_passage"
    elif record_id.startswith("FB-"):
        found = next((item for item in data["feedback"] if item["feedback_id"] == record_id), None)
        if not found:
            return None
        row = found
        source_id = found["source_id"]
        kind = "synthetic_feedback"
    elif record_id == "sales:category":
        profiles = _period_sales(data)
        row = {
            "category": data["scope"]["category"],
            "period": analyze()["period"],
            "style_count": len(profiles),
            "styles": [{"style_id": style_id, **metric} for style_id, metric in profiles.items()],
            "calculation_notes": ["revenue is synthetic MSRP × (1 − discount) × units; it is not source revenue", "return rate is return units divided by units", "stock coverage is separately shown per style"],
        }
        source_id = "SRC-DEMO-SALES-01"
        related_source_ids = ["SRC-DEMO-CATALOG-01"]
        kind = "synthetic_category_sales_aggregate"
    elif ":" in record_id:
        style_id, metric_name = record_id.split(":", 1)
        product = next((item for item in data["products"] if item["style_id"] == style_id), None)
        if not product:
            return None
        sales_profile = next((item for item in data["sales_profiles"] if item["style_id"] == style_id), None)
        inventory = next((item for item in data["inventory"] if item["style_id"] == style_id), None)
        row = {"product": product, "metric": metric_name}
        if metric_name in {"sales", "units", "weekly-average"} and sales_profile:
            row["sales_observation"] = {
                "weekly_units": sales_profile["weekly_units"],
                "units_total": sum(sales_profile["weekly_units"]),
                "week_start_dates": _weeks_for_profile(sales_profile),
                "channel": sales_profile["channel"],
                "discount_rate": sales_profile["discount_rate"],
                "return_units": sales_profile["return_units"],
                "stockout_days": sales_profile["stockout_days"],
            }
            source_id = sales_profile["source_id"]
            kind = "synthetic_sales_aggregate"
        elif metric_name == "inventory" and inventory:
            row["inventory_snapshot"] = inventory
            source_id = inventory["source_id"]
            kind = "synthetic_inventory_snapshot"
        else:
            source_id = product["source_id"]
            kind = "synthetic_product_catalog"
    else:
        return None
    related = [sources[key] for key in related_source_ids]
    return {"record_id": record_id, "kind": kind, "record": row, "source": sources[source_id], "related_sources": related}
