"""Local-only web prototype server; stdlib only, no external provider calls."""

from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import analytics, fixtures, planning_operations, repository, retrieval, synthetic_scenario


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WEB_ROOT = REPOSITORY_ROOT / "web" / "prototype"
PIPELINE_DOC = REPOSITORY_ROOT / "docs" / "design" / "hm-kaggle-data-pipeline.md"
MAX_BODY_BYTES = 1_000_000


class PrototypeHandler(BaseHTTPRequestHandler):
    server_version = "VOGUEPrototype/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep local query terms, brief text, and review content out of logs.
        return

    def _send(self, status: int, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status: int, payload: object) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("잘못된 요청 크기입니다.") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("요청 본문은 1MB 이하여야 합니다.")
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("JSON 객체 형태의 요청이 필요합니다.")
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/api/health":
                repository.initialize()
                self._json(200, {"ok": True, "mode": "local-prototype-with-separate-hm-analysis"})
            elif path == "/api/bootstrap":
                self._json(200, {
                    "analysis": analytics.analyze(), "brief": repository.get_brief(),
                    "brief_versions": repository.list_brief_versions(),
                    "variants": repository.list_variants(), "evaluations": repository.list_evaluations(),
                })
            elif path == "/api/hm-analysis":
                analysis = fixtures.get_hm_analysis()
                if analysis is None:
                    self._json(404, {"error": "H&M Kaggle 데이터 분석 산출물이 없습니다. 데이터 파이프라인을 먼저 실행해 주세요."})
                else:
                    self._json(200, analysis)
            elif path == "/api/hm-planning-analysis":
                analysis = fixtures.get_hm_planning_analysis()
                if analysis is None:
                    self._json(404, {"error": "Article 기준 상품기획 분석이 없습니다. 분석 단계를 먼저 실행해 주세요."})
                else:
                    self._json(200, analysis)
            elif path == "/api/hm-planning-reviews":
                self._json(200, {"reviews": repository.list_hm_planning_reviews()})
            elif path == "/api/hm-planning-briefs":
                self._json(200, {"briefs": repository.list_hm_planning_briefs()})
            elif path == "/api/hm-brief-reviews":
                self._json(200, {"reviews": repository.list_hm_brief_reviews()})
            elif path == "/api/data-status":
                self._json(200, planning_operations.get_data_status())
            elif path == "/api/synthetic-scenario":
                self._json(200, synthetic_scenario.analyze_scenario(synthetic_scenario.load_scenario()))
            elif path == "/api/planning/line-plans":
                self._json(200, planning_operations.list_records("line_plans"))
            elif path == "/api/planning/markdown-reviews":
                self._json(200, planning_operations.list_records("markdown_reviews"))
            elif path == "/api/planning/kpi-definitions":
                self._json(200, planning_operations.list_records("kpi_definitions"))
            elif path == "/api/planning/campaigns":
                self._json(200, planning_operations.list_records("campaigns"))
            elif path == "/api/products":
                self._json(200, planning_operations.list_products())
            elif path.startswith("/api/products/"):
                style_id = path.removeprefix("/api/products/")
                product = planning_operations.get_product(style_id)
                self._json(200 if product else 404, product or {"error": "상품을 찾을 수 없습니다."})
            elif path == "/docs/hm-kaggle-data-pipeline.md":
                self._send(200, PIPELINE_DOC.read_bytes(), "text/markdown; charset=utf-8")
            elif path.startswith("/api/evidence/"):
                record_id = path.removeprefix("/api/evidence/")
                evidence = retrieval.get_evidence(record_id)
                self._json(200 if evidence else 404, evidence or {"error": "근거 기록을 찾을 수 없습니다."})
            elif path == "/api/search":
                query = parse_qs(parsed.query).get("q", [""])[0][:300]
                self._json(200, {"query": query, "results": retrieval.search_documents(query)})
            elif path.startswith("/api/variants/") and path.endswith(".svg"):
                variant_id = path.removeprefix("/api/variants/").removesuffix(".svg")
                image = repository.get_variant_image(variant_id)
                if image is None:
                    self._json(404, {"error": "시안을 찾을 수 없습니다."})
                else:
                    self._send(200, image.encode("utf-8"), "image/svg+xml; charset=utf-8")
            elif path == "/" or path.startswith("/assets/"):
                relative = "index.html" if path == "/" else path.removeprefix("/assets/")
                target = (WEB_ROOT / relative).resolve()
                if WEB_ROOT.resolve() not in target.parents and target != WEB_ROOT.resolve():
                    self._json(404, {"error": "Not found"})
                    return
                if not target.is_file():
                    self._json(404, {"error": "Not found"})
                    return
                mime, _ = mimetypes.guess_type(target.name)
                charset = "; charset=utf-8" if mime and (mime.startswith("text/") or mime in {"application/javascript", "application/json"}) else ""
                self._send(200, target.read_bytes(), (mime or "application/octet-stream") + charset)
            else:
                self._json(404, {"error": "Not found"})
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._json(500, {"error": str(exc)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._body()
            if path == "/api/brief":
                self._json(201, repository.save_brief(payload))
            elif path == "/api/variants":
                brief = repository.get_brief()
                requested_version = payload.get("brief_version")
                if requested_version != brief["version"]:
                    raise ValueError("브리프가 변경되었습니다. 최신 버전을 저장한 뒤 시안을 만들어 주세요.")
                self._json(201, {"variants": repository.generate_variant(payload, str(payload.get("image_type", "product")), int(payload.get("count", 3)))})
            elif path == "/api/evaluations":
                self._json(201, repository.save_evaluation(payload))
            elif path == "/api/hm-planning-reviews":
                analysis = fixtures.get_hm_planning_analysis()
                if analysis is None:
                    raise ValueError("H&M 상품기획 분석 결과가 없습니다.")
                self._json(201, repository.save_hm_planning_review(payload, analysis))
            elif path == "/api/hm-planning-briefs":
                analysis = fixtures.get_hm_planning_analysis()
                if analysis is None:
                    raise ValueError("H&M 상품기획 분석 결과가 없습니다.")
                self._json(201, repository.save_hm_planning_brief(payload, analysis))
            elif path == "/api/hm-brief-reviews":
                self._json(201, repository.save_hm_brief_review(payload))
            else:
                self._json(404, {"error": "Not found"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except OSError as exc:
            self._json(500, {"error": str(exc)})


def main() -> None:
    repository.initialize()
    host = os.getenv("VOGUE_HOST", "127.0.0.1")
    port = int(os.getenv("VOGUE_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), PrototypeHandler)
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    print(f"VOGUE prototype running at http://{display_host}:{port} (local only; synthetic demo and separate H&M analysis)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local prototype.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
