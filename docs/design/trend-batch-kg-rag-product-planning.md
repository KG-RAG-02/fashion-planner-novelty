# TrendBatch candidate-planning library

## 적용 범위

이 모듈은 P06 `/runs`와 별도로 유지되는 API-neutral 라이브러리 prototype입니다. P08의 `vogue-handoff/0.3` 요청, 현재 Draft 생성, product/outfit 이미지 생성 또는 P07 handoff의 일부가 아닙니다. 이 문서의 모델·점수·요청 예시는 HTTP 계약으로 사용하면 안 됩니다.

## 구성

- `domain/trend_batch.py`: TrendBatch 입력 모델과 구조 검증
- `domain/trend_evaluator.py`: Evidence resolver 경계를 이용한 Trend × Category 평가
- `domain/candidates.py`: Existing/New 후보, 점수 설명과 다양성 선택
- `domain/retrieval.py`, `sources/hybrid_retriever.py`: 독립 retrieval interface와 실험용 구현
- `workflows/trend_planning.py`: API-neutral orchestration/use case

이 라이브러리는 별도 단위 테스트를 가지며 active HTTP server에서 import되지 않습니다. 운영 taxonomy, resolver, 기업 데이터 adapter, 결과 저장, HTTP endpoint는 제공하지 않습니다. 점수는 승인된 시장 성과나 상품 성공도를 뜻하지 않습니다.

## 변경·검증 원칙

변경 시 해당 domain 및 workflow 테스트를 실행합니다. 새 HTTP endpoint나 P08 연결을 추가할 때는 별도 계약 합의와 adapter를 먼저 정의하고 이 prototype의 dataclass를 wire contract로 노출하지 않습니다.
