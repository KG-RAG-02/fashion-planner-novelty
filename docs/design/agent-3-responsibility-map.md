# P06 · P07 · P08 책임 경계

## 현행 흐름

```text
사용자 요청 → P08이 Trend 조회 → P08이 Stock 조회
→ P08이 P06 `/runs` 호출 → P06이 초안과 product/outfit 이미지 반환
→ P08이 P06 프로필을 바탕으로 P07 `/reviews` 호출
→ P08이 결과와 planning board를 통합
```

## 담당 범위

- **P06:** P08이 전달한 PlanningRequest, Trend, Stock 결과 검증·분석; 근거와 출처가 구분된 신제품 초안 생성; 동일 프로필 기반 product/outfit 이미지 생성; artifact 메타데이터 반환.
- **P07:** P08이 전달한 허용 상품 필드를 사용해 sales/market review 수행. P06은 P07을 호출하지 않으며 P07 결과를 입력으로 받지 않습니다.
- **P08:** Trend/Stock/P06/P07 호출 순서, 요청·응답 검증, review 호출, 통합 응답과 planning board 생성.

현재 P06 endpoint와 입력·출력은 [runbook](prototype-runbook.md), [계약 호환성 메모](../../contracts/http-handoff-v0.3.md), [repository boundary](../repository-boundaries.md)에 정의합니다.
