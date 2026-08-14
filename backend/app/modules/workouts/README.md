# Workouts module

Wave 7A는 공개 `FINAL_ROUTINE` 또는 허용된 `REST` 선택, workout session 생성·시작,
운동 블록 `PENDING`/`COMPLETED` mutation, 타이머 이력과 계획 외 추가 활동을 관리합니다.
`REST`에는 세션을 만들지 않습니다. 공식 완료 근거는 사용자가 명시한 블록 체크뿐이며,
타이머·웨어러블·캘린더·추가 활동은 블록이나 세션 상태를 변경하지 않습니다.

세션 종료와 안전 중단은 후속 Wave 7B가 담당합니다. 다만 종료 상태이거나 `ended_at`이 기록된
세션은 이 모듈의 start·block·timer·additional-activity mutation에서 모두 수정할 수 없습니다.
