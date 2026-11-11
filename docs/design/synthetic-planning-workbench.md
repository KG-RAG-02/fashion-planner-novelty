# 합성 상품기획 데이터와 R2 workbench

- 상태: 로컬 fixture + R2 versioned DuckDB 읽기 adapter · 실제 회사 내부 자료 연결 없음
- 데이터셋: `SYNTHETIC-PLANNING-WORKBENCH-SEED-20261110`
- Snapshot date: `2026-11-11`
- 데이터카드: [Synthetic planning workbench data card](../../data/fixtures/synthetic_planning_workbench/DATA_CARD.md)

## 목적과 경계

이 fixture와 CLI는 카탈로그, 명세서, 브리프, 가이드 문서, Evidence 관계 및 입력 상태를 개발·테스트하기 위한 가상 예시입니다. 가상 브랜드·상품·SKU·날짜·수치·문장은 실제 회사·정책·고객·시장·사업 결과를 나타내지 않습니다. 문서의 `approved_example`은 **합성 데이터셋 안에서 검색 규칙을 시험하기 위한 상태 이름**일 뿐 회사 승인 상태가 아닙니다.

Project_06 초안은 기존 `/api/planning-draft` 경로와 규칙 기반 생성기를 사용합니다. `VOGUE_SYNTHETIC_PLANNING_RAG_ENABLED=true`이면 기본 source `r2`에서 versioned 병합 DuckDB를 내려받아 read-only 모드로 열고, `synthetic_*` 테이블을 검색합니다. `VOGUE_SYNTHETIC_PLANNING_RAG_SOURCE=local`은 fixture 검증용 선택지입니다. 병합 DB의 R2 경로, ETag cache, 검색 adapter, H&M 사진 참고/시각 분석 흐름은 [R2 cloud planning RAG design](r2-cloud-planning-rag.md)에 기록했습니다. 판매·시장 handoff는 여전히 Project_07의 opaque 경계를 유지하며 Project_06은 판매 지표를 계산하거나 재집계하지 않습니다.

실제 회사 자료 connector나 실제 회사 내부 지식 인덱스 연결은 없습니다. R2 image/catalog 데이터는 H&M Kaggle 공개 자료에 기반한 외부 참고로 별도 취급합니다. 합성 workbench는 별도 dataset namespace를 가진 명시적 opt-in 경로로 검색됩니다. `.env.example` 기본값은 `VOGUE_SYNTHETIC_PLANNING_RAG_ENABLED=false`이며, 활성화한 경우 source 기본값은 `r2`입니다. 일반 `authorized` 소스 정책과 섞이지 않고 `allow_synthetic`와 일치하는 dataset ID가 query 및 Evidence에 있어야 합니다. R2의 H&M 이미지 분석은 합성 회사 문서 근거로 변환되지 않습니다.

## 데이터 구성

재생성 결과에는 가상 브랜드/라인 taxonomy, 6개 의류 부문의 카탈로그 style과 SKU, 속성별 Evidence 연결, 테크팩·샘플 개발 이력·BOM 예시, 시즌 line plan, 카테고리 가이드, 가상 검토 선례, outfit 관계, Evidence/source locator/content hash, inventory snapshot, Project_06 draft 입력, Project_07 소유의 standalone handoff fixture가 포함됩니다. 기준 데이터에는 72 styles, 294 documents, 1,109 Evidence records, 73 inventory records, 13 assortment relations, 3 standalone Project_07 handoffs가 있습니다. 핵심 레코드는 실제 업무 자료처럼 보이는 구조와 필드 조합을 사용하지만 값과 문장은 전부 생성한 합성 예시이며 실제 회사 산출물로 표시하지 않습니다.

의도적 품질 사례에는 중복 SKU, 속성 누락, 끊긴 Evidence 참조, 초안 prompt injection 문구, 만료 가이드, 충돌 draft 명세, 단위·기준일 누락, `no_results`, 실제 0 수량이 포함됩니다. 품질 진단은 이를 탐지하고 보고할 뿐 데이터를 자동 수정하지 않습니다.

문서 기본 검색은 다음을 모두 확인합니다.

- `lifecycle_status=approved_example`
- 데이터셋 기준일에 문서 effective window가 유효
- 참조 Evidence가 모두 존재하고 `verified=true`
- Evidence의 `permitted_uses`에 `product_planning` 포함

초안·만료·기타 비활성 문서는 기본 검색에서 제외됩니다. `--include-inactive`는 점검을 위해 이를 노출하지만 결과에 eligibility와 제외 이유를 표시합니다. 검색 필터의 시즌/카테고리/채널 `all_synthetic`은 합성 데이터셋의 넓은 범위 예시입니다.

## 생성 재현

프로젝트 루트에서 실행합니다.

```bash
python3 scripts/generate_synthetic_planning_workbench.py --seed 20261110
```

같은 generator version과 seed는 같은 JSON을 만듭니다. `--output`으로 별도 경로를 지정할 수 있습니다. 생성기 버전, seed, snapshot date, dataset ID와 데이터 성격은 JSON metadata에 저장합니다.

## 로컬 CLI

```bash
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench list
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench schema
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench search sage --season 27SS --category outerwear
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench search 합성 --document-type guideline --include-inactive
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench compare SYN-STYLE-OUT-001 SYN-STYLE-OUT-003
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench show style SYN-STYLE-OUT-001
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench show document SYN-DOC-GUIDE-002
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench show evidence SYN-EV-GUIDE-001
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench handoffs
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench handoffs --status error
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench quality
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench draft SYN-REQ-PLANNING-001 --output /tmp/synthetic-planning-draft.md
```

`--json`은 machine-readable 결과를 출력합니다. 모든 CLI 실행은 snapshot SHA-256, 실행 명령·필터, 입력 snapshot을 기준으로 결정되는 `run_id`를 함께 제공합니다. `--dataset`은 subcommand보다 앞에 둡니다.

`search`는 활성 합성 문서 및 상품 필드를 조회하고, `compare`는 입력된 상품 속성의 일치·차이·누락만 보여줍니다. 점수·수요 추정·후보 우선순위를 산출하지 않습니다. `handoffs`는 Project_07 책임을 표시한 standalone 합성 `partial`, `no_results`, `error` 예시를 확인합니다. `draft`는 합성 planning request를 기존 내부 draft 경로에 넣고 Evidence와 source locator를 포함한 Markdown 검토 초안을 만듭니다. 이 경로는 실제 운영 생성기가 합성 데이터를 기본으로 사용한다는 뜻이 아닙니다.

## 검증

```bash
PYTHONPATH=src python3 -m unittest tests.test_synthetic_planning_workbench -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

테스트는 seed 재현, non-synthetic 데이터 거부, 기본 검색의 draft/expired 제외, 품질 오류 탐지, `no_results`와 quantity 0 구분, Evidence 추적, Project_07 handoff 상태 보존, draft의 synthetic 고지 및 prompt injection 문서 격리를 확인합니다. 이는 합성 파이프라인 동작만 검증하며, MD 효용·시장성·실제 회사 정책에 대한 검증이 아닙니다.

## Project_06 RAG 연결

`SyntheticWorkbenchRetriever`는 taxonomy, catalog comparison, planning reference, precedent, assortment relation, exact Evidence lookup 목적을 분리해 제공합니다. JSON fixture와 R2 DuckDB adapter가 같은 필터·Evidence 계약을 공유합니다. 결과는 source allowlist, 문서 유형, 시즌·카테고리·역할, lifecycle, 유효기간, Evidence 상태, permitted use로 거릅니다. 반환 ref에는 dataset/snapshot ID, R2 object version, 합성 표시, source locator, content hash, Evidence가 뒷받침하는 속성 경로, retrieval run ID를 보존합니다. 검색은 deterministic lexical 기준선이며 vector/graph 인덱스가 아닙니다.

API는 환경변수가 켜졌을 때 R2 adapter를 자동 선택합니다. 검색 실패/빈 결과는 각 목적별 상태로 반환하고 초안 생성을 계속합니다. 이미지 참고는 H&M 후보 사진을 최대 3장까지 R2에서 선택·분석한 뒤 `hm_visual_references` 별도 응답으로 돌려줍니다. 사진 관찰은 Evidence가 연결된 합성 자료의 주장으로 쓰이지 않습니다. Project_07은 이 검색 계획에 사용되지 않으며 기존 opaque payload 보존 경계를 유지합니다.

## 실제 자료 전환 시 필요한 승인

실제 자료를 연결하기 전에 각 자료 소유자와 승인된 용도, 접근 권한, 개인정보/비밀정보 포함 여부, 저장·보존·삭제 기간, 갱신·버전 규칙, 문서 상태와 만료 방식, 품질 책임자, 로그/감사 정책, 검색·모델 전송 허용 여부를 합의해야 합니다. 승인 후에도 실제 자료는 합성 fixture와 다른 환경·source allowlist·index version으로 분리합니다. 판매·시장 지표는 Project_07 책임과 계약을 유지합니다.
