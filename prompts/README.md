# 프롬프트

novelty 서비스가 쓰는 프롬프트 템플릿이다. 실행 코드는 `fashion_planner_novelty.domain.prompt_registry`로 읽고, 어느 디렉터리를 쓸지는 `manifest.json`이 정한다.

| 구성 요소 | 디렉터리 | 쓰는 곳 |
|---|---|---|
| `text_planning` | `text_planning/` | 텍스트 LLM 기획(`/runs`에서 기본으로 켜짐, API 키가 있을 때). 시스템 템플릿과 사용자 템플릿이 있다. 데이터에는 서비스가 고른 주 트렌드 하나(`primary_trend`)만 들어가고, 모델은 다른 트렌드를 섞지 않도록 지시받는다 |
| `concept_image` | `concept_image/` | 상품·착장 이미지 호출의 시스템 지시. 이미지 사용자 지시는 같은 상품 사양 JSON으로 코드(`workflows/draft_artifacts.py`)가 만든다 |

디렉터리마다 `system_template.md`(원본)와 `rendered_system.md`(검토용 사본)가 있다. `text_planning/user_template.md`는 이름 있는 자리표시자만 받는다. 신뢰할 수 없는 요청 데이터는 길이를 제한해 JSON으로 직렬화한 뒤 넣는다.

## 프롬프트를 바꿀 때

1. `system_template.md`나 `user_template.md`를 고친다. 이전 내용은 Git 히스토리로 추적한다.
2. `PYTHONPATH=src python3 scripts/render_prompts.py`로 `rendered_system.md`를 다시 만든다.
3. 프롬프트 레지스트리, 기획, 이미지 관련 테스트를 돌리고 렌더 결과의 diff를 검토한다.

프롬프트를 바꾸면 모델 동작이 바뀔 수 있다. 바꿨다는 사실만으로 품질이 나아졌다고 볼 수 없다. 입력 길이 제한을 지키고, 근거가 있는 사실·제안·미확인 값의 구분을 유지한다. 두 이미지가 같은 상품 사양 해시를 쓴다는 것은 사양이 같다는 뜻일 뿐, 그려진 픽셀이 같은 디자인이라는 증거는 아니다.
