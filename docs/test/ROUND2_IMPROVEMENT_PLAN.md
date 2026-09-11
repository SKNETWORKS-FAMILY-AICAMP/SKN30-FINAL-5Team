# 2차 멀티에이전트 품질 개선·평가 계획

## 1. 기준선과 목적

- 1차 기준선: commit `3b78731`, tag `evaluation-v1-baseline`
- 1차 결론: 안전성은 확인했지만 Multi-Agent의 비용 대비 우월성은 입증하지 못했다.
- 2차 목적: Safety 불변식을 유지하면서 D-5 가용성, advisory 반영, token/latency를 개선하고
  held-out Human 평가로 Single-Agent RAG 대비 실질적 품질 차이를 검증한다.
- 1차 산출물은 수정하지 않는다. 2차 산출물은 `results/round2/`와 별도 Phase 문서에 저장한다.

## 2. 개선 항목

| ID | 변경 | 기대 효과 | 안전 경계 |
|---|---|---|---|
| R2-1 | Training READY + advisory NEEDS_INPUT 허용 | 불필요한 fallback 감소 | Training/기술 실패는 계속 차단 |
| R2-2 | Recovery/Feasibility 역할별 최소 payload | 평균 token·latency 감소 | envelope/hash/allowlist 유지 |
| R2-3 | advisory status·code 처리 지침 강화 | Coordinator 조정 추적성 향상 | code를 하드 규칙으로 강제하지 않음 |
| R2-4 | prompt version 분리 | v1/v2 재현성 확보 | model/catalog/policy 고정 |

## 3. 사전 등록 성공 기준

| 지표 | 통과 기준 |
|---|---:|
| Safety golden pass rate | 1.000 |
| Critical / unsafe plan | 0건 |
| 실-provider workflow completion | 0.950 이상 |
| Multi - Single RAG Human mean | +0.20 이상 |
| v1 Multi 대비 평균 total token | 25% 이상 감소 |
| Multi P95 latency | 30초 이하 |
| conflict/complex case plan rate | Single RAG 이상 |

한 기준이라도 미달하면 “Multi-Agent가 더 유효하다”는 결론을 내리지 않는다. Judge 점수는 보조
지표이며 Human 결과를 대체하지 않는다.

## 4. 데이터와 비교 통제

- 기존 20 case는 구현 회귀와 tuning에만 사용한다.
- held-out은 최소 30 case, 권장 50~100 case로 구성한다.
- safety, conflict, limited-time, missing wearable, recovery, equipment/location, provider failure를
  층화한다.
- Multi-Agent와 Single-Agent RAG는 같은 model version, catalog, policy, 요청 snapshot,
  compiler, validator를 사용한다.
- 표시 순서를 무작위화하고 architecture label을 숨긴다.
- PM과 개발리드는 합의 전 독립 점수를 각각 남긴다.

## 5. 실행 게이트

1. 계약·unit·privacy·golden/safety 테스트
2. 기존 20 case 오프라인 회귀
3. 실-provider 5~10 case smoke 및 LangSmith span 확인
4. 10~20 case 유료 pilot, 실패·token·latency 검토
5. held-out 전체 실행
6. 독립 blind Human 평가
7. Judge calibration을 별도 산출
8. 성공 기준 판정과 최종 보고

유료 단계마다 실제 run 수, 예상 최대 호출 수, 사용 model을 manifest에 기록한다. smoke 또는 pilot에서
unsafe plan, critical failure, privacy 위반이 1건이라도 나오면 전체 실행을 중단한다.

## 6. 결과 판정

- 모든 기준 통과: Multi-Agent v2 승격 후보
- 안전 통과, 품질/비용 미달: 서비스 안전성은 유지하되 architecture 우월성 결론 보류
- 가용성만 개선: D-5 수정은 유지하고 prompt/구조는 추가 실험
- Single RAG가 동등 이상: multi-agent 단순화 또는 조건부 호출을 후속 ADR로 검토

## 7. 진행 현황 (2026-09-11)

- R2-1~R2-4 구현 완료
- 오프라인 회귀와 전체 자동 테스트 통과
- specialist payload byte 49.8192%, 전체 평가 prompt token 예측 30.7776% 감소
- 실-provider smoke: 외부 전송 범위에 대한 구체적 재승인 대기
- 상세: `docs/test/ROUND2_LOCAL_RESULTS.md`
