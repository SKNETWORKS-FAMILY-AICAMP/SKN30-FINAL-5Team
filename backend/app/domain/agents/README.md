# Multi-agent domain core

이 디렉터리는 Training·Recovery·Safety·Feasibility의 구조화 proposal 계약과 결정적
Coordinator 경계를 소유합니다. Agent는 검수된 공통 후보를 제한하거나 선택하며 카탈로그
밖 운동을 생성하지 않습니다.

현재 구현 범위는 versioned internal proposal schema, 네 필수 Agent의 fail-closed 병렬
runner, 공통 domain candidate 중 하나를 선택하는 결정적 Coordinator입니다. 정규화 context,
개별 Agent 정책, persistence와 공개 summary는 후속 승인·작업에서 추가합니다.

규칙:

- 필수 Agent 하나라도 누락되거나 실패하면 운동 계획 성공으로 진행하지 않습니다.
- Safety status와 veto는 runner가 수정하지 않습니다.
- Coordinator는 정확히 네 proposal을 순서와 무관하게 검증하고 Safety veto, 요청 시간,
  Feasibility, Recovery, Training 순으로 후보를 제한합니다.
- 후보는 `DurationPlan`으로 요청 시간과 정확히 일치해야 하며 Coordinator 입력에 없는 후보나
  운동을 생성할 수 없습니다.
- `REST`, `STOP_AND_SEEK_HELP`, `NEEDS_INPUT`, `FAILED`에는 선택 candidate가 없습니다.
- failure proposal에는 예외 메시지나 입력 snapshot을 복사하지 않습니다.
- 생년월일, 만 나이, 직접 식별자, 원시 건강·웨어러블 데이터는 Agent 입력에 넣지 않습니다.

routine application service는 ORM이나 repository 객체 대신 `CoordinatorCandidate`로 변환한
공통 후보를 전달해야 합니다. Coordinator 결과의 저장 및 공개 API 매핑은 decision application
service의 책임입니다.
