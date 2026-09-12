# ADR-0022: repair 도달 가능성과 specialist 실패 코드 분리

- 상태: ACCEPTED
- 날짜: 2026-09-11
- 소유자: AI/data lead
- 승인자: 개발리드·PM 권한 보유 프로젝트 오너(2026-09-11 대화 승인)
- 관련 ADR: ADR-0015의 repair 라운드와 ADR-0021의 readiness 게이트를 좁게 수정한다.
  나머지 결정은 유지한다.

## 배경

2차 held-out 유료 평가(`docs/test/ROUND2_HELDOUT_RESULTS.md`)에서 Multi-Agent 29 run의
`repair_attempts`가 전부 0이었다. 처음에는 "repair가 필요 없었다"로 읽었으나 추적 결과
**"repair가 불가능했다"** 였다.

`validate_plan_integrity`는 위반의 repairable 판정에 `has_approved_alternative`를 요구했고,
이 값은 `IntegrityValidationContext.approved_safe_alternative_ids`에서 온다. 그런데 이 필드를
채우는 프로덕션 코드 경로가 없다. 기본값은 `()`이고, 프로덕션의 유일한 생성부인
`shadow_runtime._IntegrityValidator`는 `fallback_plan_validation`만 전달하며, `demo_runtime`은
같은 validator를 재사용한다. 값을 설정하는 곳은 unit test뿐이다.

따라서 `IntegrityValidationStatusCode.REPAIRABLE`은 실제 실행에서 발생할 수 없었고,
`routing.after_validation`의 `coordinator_repair` 분기는 도달하지 않았다. repair 노드, repair
prompt, `repair_attempt` 상태, `REPAIR_ATTEMPT_EXHAUSTED` 코드가 모두 존재하는데 동작하지
않았다.

SQ-HELD-023이 그 손실이다. 위반 코드는 `PLAN_EXERCISE_FAMILY_REPEATED`로, 조건부 복구 대상
집합에 포함되어 있었는데 승인된 대체 운동이 없어 복구 시도 없이 결정적 fallback으로 갔다.

두 번째 문제는 같은 평가에서 드러났다. `nodes._run_specialist`가 서로 다른 두 원인에 같은
실패 코드 `V3_TRAINING_NOT_READY`를 썼다. 하나는 proposal이 `validate_proposal`을 통과하지
못한 계약 위반이고, 다른 하나는 proposal은 유효하나 agent가 스스로 `READY`가 아니라고
판단한 경우다. 대응이 완전히 다른데 산출물에서 구분할 수 없었다.

## 결정

1. repairable 판정을 두 부류로 분리한다.
   - **substitution 부류**(`_SUBSTITUTION_REPAIRABLE`): `SAFETY_EXCLUDED_EXERCISE_INCLUDED`.
     Safety가 제외한 운동을 교체하려면 Safety가 승인한 대체 운동이 필요하므로 기존처럼
     `approved_safe_alternative_ids`를 요구한다. **이 부분은 변경하지 않는다.**
   - **pool 부류**(`_POOL_REPAIRABLE`): 나머지 shape·dosage 위반. pool 자체가 승인된 후보
     집합이므로(PostgreSQL이 eligibility를 결정하고 envelope 제외가 snapshot 생성 전에
     적용된다) pool에 Safety가 제외하지 않은 운동이 하나라도 있으면 복구 가능으로 본다.
2. repair 라운드는 계속 1회로 제한한다(`repair_attempt == 0`).
3. specialist 실패 코드를 셋으로 분리한다.
   - `V3_{ROLE}_NO_PROPOSAL`: adapter가 proposal을 반환하지 않음
   - `V3_{ROLE}_PROPOSAL_INVALID`: proposal이 hash·role·pool 계약을 위반
   - `V3_TRAINING_NOT_READY`: proposal은 유효하나 Training이 `READY`가 아니라고 자체 판단
4. SafetyPolicyEngine, ConstraintEnvelope, compiler, integrity validator의 **위반 판정 규칙은
   변경하지 않는다.** 바뀌는 것은 "이미 판정된 위반에 repair 라운드를 쓸 가치가 있는가"뿐이다.

## 이유

- **안전 경계는 넓어지지 않는다.** repair 산출물은 같은 `validate_plan_integrity`가
  `repair_attempt=1`로 다시 검증한다. 통과하면 모든 bound가 성립한다는 뜻이고, 실패하면
  `REPAIR_ATTEMPT_EXHAUSTED`가 붙어 오늘과 동일하게 결정적 fallback으로 간다. 즉 이 변경이
  통과시킬 수 있는 계획은 repair 없이도 통과했을 계획뿐이다.
- `_POOL_REPAIRABLE`의 전제는 코드에 이미 적혀 있었다. 기존 주석은 shape 위반의 복구
  가능성을 "pool always reserves candidates for every phase"로 정당화했다. 즉 설계 의도는
  pool이 근거였는데 구현은 승인 대체 목록을 요구했다.
- `APPROVED_SAFE_EXERCISE_UNAVAILABLE`은 `not pool.exercises`일 때 발생한다. validator 자신이
  "승인된 안전 운동의 가용성"을 pool의 비어 있지 않음으로 판정하고 있다.
- 실패 코드 분리는 관측성 변경이다. `failure_code`는 `String(128)`이고 enum 제약이 없으므로
  마이그레이션이 필요 없다.

## 결과

- repair 노드가 실제로 도달 가능해진다. shape·dosage 위반은 결정적 fallback 전에 Coordinator
  호출 1회를 더 쓴다. 비용 상한은 run당 1회다.
- Multi-Agent의 계획 생성률은 오를 수 있으나 **이 ADR은 그것을 주장하지 않는다.** 재측정으로
  확인한다.
- `test_exact_duration_mismatch_is_repairable_only_with_approved_alternative`는 옛 규칙을
  그대로 단언하고 있었으므로 새 규칙에 맞게 다시 썼다. 안전 측 절반은
  `test_a_safety_exclusion_still_needs_an_approved_substitute`로 남긴다.

## 남은 결정 (이 ADR 범위 밖)

`approved_safe_alternative_ids`를 누가 산출하는가는 여전히 미결이다. 후보는 Qdrant snapshot
loader와 배포 안전 규칙(`safety_rules.jsonl`)이다. 이것이 정해지기 전까지
`SAFETY_EXCLUDED_EXERCISE_INCLUDED`는 실질적으로 복구 불가이며, 해당 계획은 결정적
fallback으로 간다. 안전한 동작이므로 이 ADR은 그 상태를 유지한다.

## 대안

- **필드를 임의 값으로 채우기**: pool의 일부를 "승인된 대체 운동"으로 간주하는 방법. Safety가
  승인한 적 없는 운동에 승인 의미를 부여하므로 기각했다.
- **`has_approved_alternative` 조건만 삭제**: `SAFETY_EXCLUDED_EXERCISE_INCLUDED`까지 pool
  기준으로 복구 가능해진다. 안전 교체를 근거 없이 허용하므로 기각했다.
- **repair 라운드 제거**: 도달 불가 코드를 지우는 선택. ADR-0015가 repair를 Coordinator 출력
  회복 수단으로 정했고 제거는 그 결정을 뒤집으므로 기각했다.
