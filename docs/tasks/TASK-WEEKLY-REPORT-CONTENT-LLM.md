# TASK-WEEKLY-REPORT-CONTENT-LLM

## Scope

- 주간 리포트를 수행 기록 → 피드백 → 컨디션/통증 → 실제 추천 조정 → 다음 주 추천 순서로 제공한다.
- 1~3번의 수치·판정은 저장된 운동 수행, 피드백, 연결된 일일 체크인에서 결정적으로 집계한다.
- 4~6번의 사용자 문구만 OpenAI narration으로 생성하고 검증 실패 시 템플릿으로 대체한다.
- 기존 acknowledgement와 다음 주 계획 확정 gate는 유지한다.

## Acceptance criteria

1. 목표 횟수, 완료, 부분 수행, 완료율과 첫 주를 제외한 지난주 대비가 보인다.
2. 완료, 부분 수행, 휴식, 안전 중단, 총 운동 시간, 최빈 운동 유형, 체감 난이도가 보인다.
3. 피로 변화, 통증 횟수, 실제 저장된 휴식·부분 수행·중단 사유가 보이며 없는 사유를 추정하지 않는다.
4. 실제 추천 action과 집계 근거만 사용해 조정 설명을 생성한다.
5. 다음 주 강도, 운동량, 시간, 통증 대응 방향을 구조화된 문구로 생성한다.
6. 한 줄 코치는 잘한 점, 주간 요약, 다음 주 응원을 포함하며 안전 중단 시 진지한 톤을 쓴다.
7. LLM 장애에도 리포트 생성이 성공하고 결정적 fallback 문구가 제공된다.
8. 기존 리포트와 클라이언트는 additive optional 필드 없이도 계속 조회·표시된다.

## Expected changes and risks

- Backend: weekly report ports, service, narration, repository, schemas, tests.
- Frontend: typed response, weekly report summary, preview/test fixtures and component tests.
- Contracts: API, domain rules, data model, narration boundary.
- API: optional response fields만 추가한다. endpoint와 request는 바꾸지 않는다.
- Database: migration 없음. 기존 column과 versioned JSON snapshot을 사용한다.
- Privacy: LLM에는 식별자, 자유서술, 통증 부위·NRS, 원시 체크인을 보내지 않는다.
- Compatibility: 과거 리포트는 기존 `decision_summary`, `next_action`, `summary`로 표시한다.
