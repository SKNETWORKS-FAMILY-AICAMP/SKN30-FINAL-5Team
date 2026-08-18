# Golden scenarios

버전화된 합성 입력과 기대 action/safety/exclusion/time 결과를 저장합니다. 실제 개인정보,
원시 건강 기록, token, 현재 시각, 무작위 UUID 또는 외부 API를 사용하지 않습니다.

`decision_golden_fixtures.py`는 framework-independent Coordinator/replay 계약을 고정합니다.
`decision_service_golden_fixtures.py`는 운영 `DecisionService`, 안전 엔진, 네 specialist agent와
Coordinator에 합성 assembly만 제공하며 안전 판단을 테스트 코드에 복제하지 않습니다.

## Wave 4 decision matrix

| scenario code | 입력·요청 시간 | 불편/주의 부위 | wearable | proposal 핵심 | 최종 action / safety / veto | 제외 → 대체 | 선택 candidate / 시간 | fallback / replay |
|---|---|---|---|---|---|---|---|---|
| `HEALTHY_KEEP` | LOW, 40분 | 없음 | 선택 입력 없음 | 4 READY, Safety PASS | KEEP / PASS / false | 없음 | original / 2400초 | template / 동일 |
| `REQUESTED_DURATION_PRESERVING_DOWNSHIFT` | MODERATE fatigue, USER_OVERRIDE 30분 (profile 40분) | 없음 | 선택 입력 없음 | Recovery DOWNSHIFT | DOWNSHIFT / PASS / false | 없음 | approved-downshift / 1800초 | template / 동일 |
| `KNEE_MODERATE_APPROVED_REPLACEMENT` | LOW, 40분 | KNEE MODERATE | 없음 | Safety CHANGE, excluded base | CHANGE / REVISE / true | base → 승인 alternative | safety-change / 2400초 | template / 동일 |
| `WEARABLE_MISSING_MANUAL_FALLBACK` | 수동 check-in, 40분 | 없음 | 미연결 | 4 READY | KEEP / PASS / false | 없음 | original / 2400초 | manual / 동일 |
| `LLM_DISABLED_OR_FAILED_SAME_DECISION` | LOW, 40분 | 없음 | 없음 | 두 mode에서 동일 | KEEP / PASS / false | 없음 | original / 2400초 | template / 동일 |
| `SAFETY_VETO_BYPASS_BLOCKED` | LOW, 40분 | KNEE SEVERE | 없음 | Safety REST, 다른 agent plan 제안 가능 | REST / BLOCKED / true | 계획 없음 | 없음 / 없음 | template / 동일 |
| `KNEE_MILD_CAUTION_DOWNSHIFT` | LOW, 40분 | KNEE MILD | 없음 | Safety DOWNSHIFT, no veto | DOWNSHIFT / REVISE / false | 제거 없음 | approved-downshift / 2400초 | template / 동일 |
| `KNEE_MODERATE_APPROVED_ALTERNATIVE` | LOW, 40분 | KNEE MODERATE | 없음 | Safety CHANGE, excluded base | CHANGE / REVISE / true | base → 승인 alternative | safety-change / 2400초 | template / 동일 |
| `CHRONIC_KNEE_ATTENTION_CAUTION` | LOW, 40분 | 당일 불편 없음, KNEE 주의 | 없음 | Safety DOWNSHIFT, no veto | DOWNSHIFT / REVISE / false | 제거 없음 | approved-downshift / 2400초 | template / canonical 동일 |

기존 USER_OVERRIDE, MILD EXCLUDE 레코드 해석, SEVERE REST, 중대 이상반응 STOP,
필수 agent 실패 시나리오도 Coordinator/replay fixture에 유지합니다. 결정 API에는 LLM adapter가
없으므로 LLM failure mode는 외부 네트워크가 차단된 동일 production decision 경로와 template
fallback 동등성까지만 검증합니다.
