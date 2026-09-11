# ADR-0020: LangSmith provider span의 명시적 옵트인

- 상태: ACCEPTED
- 날짜: 2026-09-11
- 소유자: 개발팀장·PM 공동
- 승인자: 개발팀장·PM 승인 완료(사용자 명시 승인, 2026-09-11)
- 관련: `docs/test/service_test_master_prompt.md` PHASE 8, `docs/TECHNICAL_PLAN.md`, ADR-0013

## 배경

기존 V3 그래프 trace는 노드 15개와 상태 전이를 보여 주지만 provider 호출을
`tracing_context(enabled=False)`와 빈 callback 목록으로 이중 차단한다. 따라서 prompt,
모델 원문 응답, provider token span은 LangSmith에서 볼 수 없다.

PHASE 8 검증에서 LLM span을 제한적으로 열 필요가 확인됐지만, 이 변경은 prompt와 모델 응답을
외부 SaaS인 LangSmith에 추가 전송한다. 환경에 키가 우연히 존재하는 것만으로 전송이 시작돼서는 안 된다.

## 결정

`LLM_AGENTS_TRACING_ENABLED` 설정을 추가하고 기본값을 `false`로 둔다.

- `false`: 기존과 동일하게 tracing context와 callback을 모두 차단한다.
- `true`: provider 호출 범위에서 tracing을 명시적으로 활성화하고 ambient tracer가 연결되도록 한다.
- 실제 외부 전송에는 LangSmith API key와 tracing project 설정도 별도로 필요하다.
- production compose에는 이 값을 추가하지 않는다. 승인된 평가·staging 실행에서만 일시적으로 켠다.

## 결정 이유

기본 비활성은 기존 개인정보 경계를 보존한다. 명시적 양방향 설정은 상위 context가 tracing을
비활성화했을 때도 승인된 실행이 조용히 실패하지 않게 하며, 반대로 ambient 환경변수만으로 prompt가
유출되는 회귀를 막는다.

## 검토한 대안

- provider tracing을 항상 활성화
- 기존 차단을 유지하고 `InvocationAudit`만 사용
- prompt를 별도 파일로 저장한 뒤 수동 업로드

## 선택하지 않은 대안과 이유

- 항상 활성화는 최소 전송·기본 거부 원칙을 위반한다.
- `InvocationAudit`는 token·latency는 제공하지만 prompt/응답 span을 제공하지 않는다.
- 수동 저장·업로드는 민감 데이터 사본과 별도 보존 경계를 만든다.

## 결과와 영향

- 공개 API와 데이터베이스 스키마는 바뀌지 않는다.
- 기본 배포 동작은 바뀌지 않는다.
- 승인된 실행은 specialist와 coordinator provider span을 LangSmith에서 확인할 수 있다.
- traced run의 latency는 SaaS export 비용이 포함되므로 비추적 run과 직접 비교하지 않는다.

## 보안·개인정보·호환성 영향

prompt에는 직접 식별자, 원시 wearable sample, GPS, calendar text를 넣지 않는다. 다만
`excluded_exercise_ids`, `recovery_ceiling`, `safety_required_action_code`, 목표·장소·요청 시간처럼
건강 상태를 간접 추론할 수 있는 정규화 값과 모델 응답이 LangSmith로 전송된다.

실행 전 개발팀장·PM 공동 승인, 대상 project 확인, 보존·접근 정책 확인이 필요하다. 두 역할의 승인은
2026-09-11 사용자 명시 승인으로 확보했다. API key는 코드,
결과 파일, 로그에 기록하지 않는다.

## 아직 확정되지 않은 사항

- LangSmith project의 보존 기간과 접근자
- LangSmith project의 실제 접근자·보존 설정 증적 링크
- 최초 실전 span 확인 실행 시점

## 후속 작업

- 승인된 환경에서만 `LLM_AGENTS_TRACING_ENABLED=true`로 실행한다.
- 최초 실행 후 prompt/응답 span 존재와 직접 식별자 부재를 확인하고 결과 문서에 기록한다.
