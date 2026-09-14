# ADR-0023: Training 거절 사유와 결정적 실행 가능성 사전 검사

- 상태: ACCEPTED
- 날짜: 2026-09-12
- 소유자: 개발 리드 / AI·데이터 리드
- 승인자: 프로젝트 오너(사용자 승인, 2026-09-12)
- 관련 요구사항/이슈: `docs/test/ROUND2_HELDOUT_RESULTS.md` 12.4절

## 배경

60건 확대 평가의 planning case 54건 중 Training은 9건에서 `NEEDS_INPUT`을 반환했다.
10개 사유 문자열은 모두 duration/volume 조합 부족을 뜻했지만 표현은 9종으로 흔들렸다.
같은 9개 입력에서 Single-Agent는 8개 계획을 공통 compiler·integrity validator에 통과시켰고,
Multi-Agent의 결정적 fallback도 사용자에게 계획을 전달했다. 따라서 LLM이 만든 자유 문자열은
조합 부재의 증거로 사용할 수 없다.

## 결정

1. Training의 `NEEDS_INPUT` 사유는
   `TRAINING.DETERMINISTIC_PLAN_FEASIBILITY_UNPROVEN` 한 코드로 제한한다. 새 prompt의 adapter
   경계에서 강제하고, 기존 `specialist-agent-proposal-v1` 저장 레코드는 읽기 호환성을 유지한다.
2. Training 호출 전에 운영 graph와 동일한 결정적 fallback provider로 후보 생성을 시도한다.
3. 유효한 envelope·pool·fallback version을 참조하는 후보가 반환되면 Training payload에
   `DETERMINISTIC_PLAN_CANDIDATE_AVAILABLE`을 전달한다. 이 경우 Training은 `READY`만 반환할 수
   있고 `NEEDS_INPUT`은 domain-invalid 출력으로 처리하여 기존 bounded retry를 사용한다.
4. 후보가 없거나 사전 검사 자체가 실패하면
   `DETERMINISTIC_PLAN_FEASIBILITY_UNPROVEN`을 전달한다. 이 상태에서만 위 안정 사유 코드와 함께
   `NEEDS_INPUT`을 허용한다.
5. 이 사전 검사는 안전 판정, Coordinator, compiler 또는 최종 integrity validation을 대체하지
   않는다. 생성된 최종 계획은 종전과 동일한 하류 검증을 모두 통과해야 한다.

## 결정 이유

결정적 provider가 후보를 실제로 만들었다면 “가능한 phase·volume 조합이 없다”는 거절은
반증된다. 반대로 provider가 후보를 만들지 못했다는 사실은 탐색 공간 전체의 불가능성을
증명하지 않는다. 그래서 두 번째 상태를 `INFEASIBLE`이 아니라 `UNPROVEN`으로 명명한다.
이 비대칭은 과도한 거절을 줄이면서도 휴리스틱 실패를 거짓 불가능 판정으로 승격하지 않는다.

## 검토한 대안

### 자유 문자열을 유지하고 prompt만 수정

확대 평가에서 동일 의미가 여러 문자열로 분산되었으므로 집계와 정책 검증이 안정적이지 않다.

### fallback 실패를 `INFEASIBLE`로 판정

현재 provider는 완전 탐색기나 제약 충족 증명기가 아니다. `None`은 구현이 후보를 찾지 못했다는
뜻일 뿐, 계획이 존재하지 않는다는 증명이 아니다.

### Training의 `NEEDS_INPUT`을 완전히 제거

정규화된 입력만으로 계획을 구성하지 못하는 미래의 카탈로그·제약 조합을 안전하게 표현할
경로가 사라진다. `UNPROVEN` 상태의 제한된 거절 경로를 유지한다.

## 결과와 영향

- 결정적 후보가 있는 입력에서 Training의 확률적 거절은 최대 2회의 기존 provider 시도 안에서
  재시도된다.
- 거절 사유 집계는 하나의 안정 코드로 수렴한다.
- 사전 검사는 로컬 결정적 계산만 사용하며 별도 유료 호출을 추가하지 않는다.
- 기존 fallback 경로와 최종 안전 veto 우선순위는 변하지 않는다.

## 보안·개인정보·호환성 영향

LLM에는 이미 승인된 비식별 envelope·pool과 새 machine code 한 개만 전달한다. 직접 식별자,
원시 건강 기록, wearable 또는 calendar 데이터는 추가하지 않는다. 공개 API와 DB 스키마는
변경하지 않는다. 기존 저장 proposal도 계속 역직렬화할 수 있다. ADR-0023 구현 시 내부 Training
prompt version을 `v3-training-prompt-v11`로 올렸고, 표적 실행의 family 중복 후속 수정에서
catalog `family_code` 지침을 추가하며 `v3-training-prompt-v12`로 갱신했다. ADR-0024까지 포함한
authoritative 배포 런타임의 aggregate prompt version은 `v3-prompts-v7`이다.

## 아직 확정하지 않은 사항

- 완전한 제약 충족 증명기 도입 여부
- Single-Agent baseline에 대칭적 거절 계약을 추가할지 여부
- 변경 후 유료 held-out 재측정 시점과 예산

## 후속 작업

1. 오프라인 회귀와 golden/safety/fallback/privacy 테스트를 실행한다.
2. 다음 승인된 유료 평가에서 Training decline rate와 추가 retry 비용을 함께 측정한다.
3. `llm_plan_rate`에는 architecture-neutral 출력 계약이 결정될 때까지 계약 비대칭 주석을 유지한다.

2026-09-12 표적 유료 검증에서 1~2를 수행했다. 과거 거절 9건과 대조군 3건을 실행해
Training decline 0/9, 추가 Training retry 0회, 계획 전달·안전·workflow 1.000을 확인했다.
실제 49호출 중 기본 48호출을 넘은 1회는 Coordinator repair였다. 전체 비교 재실행과 3번은
계속 후속 범위로 남긴다.
