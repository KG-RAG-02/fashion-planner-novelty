# 계약

novelty 서비스가 orchestrator와 주고받는 HTTP 계약의 설명이다.

- [http-handoff.md](http-handoff.md): `POST /v1/agents/novelty/runs`의 요청·응답 모양과 오류 코드

기준 스키마는 orchestrator 저장소의 `contracts/agents/novelty/`에 있다. 이 저장소의 문서는 서비스 쪽에서 본 요약이다. 계약을 바꿀 때는 두 저장소를 함께 고친다. planning_request, trend_result, inventory_product_result의 스키마는 각각 그것을 만드는 서비스가 소유한다.
