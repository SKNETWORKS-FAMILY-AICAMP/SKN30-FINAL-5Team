# Multi-agent domain core

이 디렉터리는 Training·Recovery·Safety·Feasibility의 구조화 proposal 계약과 결정적
Coordinator 경계를 소유합니다. Agent는 검수된 공통 후보를 제한하거나 선택하며 카탈로그
밖 운동을 생성하지 않습니다.

현재 구현 범위는 versioned internal proposal schema와 네 필수 Agent의 fail-closed 병렬
runner입니다. 정규화 context·공통 candidate 상세 schema, 개별 Agent 정책, Coordinator,
persistence와 공개 summary는 후속 승인·작업에서 추가합니다.

규칙:

- 필수 Agent 하나라도 누락되거나 실패하면 운동 계획 성공으로 진행하지 않습니다.
- Safety status와 veto는 runner가 수정하지 않습니다.
- failure proposal에는 예외 메시지나 입력 snapshot을 복사하지 않습니다.
- 생년월일, 만 나이, 직접 식별자, 원시 건강·웨어러블 데이터는 Agent 입력에 넣지 않습니다.
