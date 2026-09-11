# PHASE 11 최종 결과 산출

- 완료일: 2026-09-11
- 상태: **COMPLETE**
- 필수 산출물: 7/7 생성 및 SHA-256 기록
- Manifest: `results/phase11_manifest.json`

## 1. 테스트 환경

Python 3.12.13, 운영과 같은 PRODUCTION 프로필, `OPENAI:gpt-5.6-terra`,
`text-embedding-3-small` 256차원 COSINE 환경에서 평가했다. 상세는 `TEST_RESULTS.md` 1절이다.

## 2. Dataset 구성

Smoke dataset 20건과 retrieval dataset 8건을 사용했다. 실-provider planning 대상은 14건이고
Human Calibration은 대표 출력 24건이다.

## 3. 사용 모델

Single LLM, Single-Agent RAG, Multi-Agent RAG 모두 같은 planning 모델을 사용했다. Judge도 같은
모델 계열이므로 self-preference 가능성을 한계로 기록했다.

## 4. 평가 방법

결정적 검사, 실 embedding retrieval, 실-provider planning, pointwise Judge, pairwise Judge,
아키텍처 비교, 실패 주입, LangSmith trace, 사람 보정 순서로 진행했다. 안전 판정은 Judge가 아니라
결정적 validator 결과를 따른다.

## 5. Deterministic Test 결과

204 run 모두 통과했고 critical failure는 0건이었다. Safety veto 이후 coordinator 우회와 compiled
plan 하류 검증을 포함한다.

## 6. Retriever 성능

실 embedding 기준 Recall@3 0.59, MRR 0.41, nDCG@5 0.49였다. Qdrant는 자격이 아니라 순위만
담당하므로 검색 누락이 안전 운동 자격을 확장하지 않는다.

## 7. Multi-Agent 품질

실-provider 14건 중 12건이 완료됐다. Agent invocation, role consistency, state consistency,
safety compliance는 모두 1.0이며 critical failure는 0건이다.

## 8. Single vs Multi 비교

공정한 주 비교 대상은 Single-Agent RAG와 Multi-Agent RAG다.

| Metric | Single Agent + RAG | Multi-Agent + RAG | Difference (Multi-Single) |
|---|---:|---:|---:|
| Constraint Satisfaction | 1.0000 | 0.8571 | -0.1429 |
| Safety Compliance | 1.0000 | 1.0000 | 0.0000 |
| Conflict Resolution | 1.0000 | 1.0000 | 0.0000 |
| Judge Score | 4.0833 | 4.4028 | +0.3195 |
| P95 Latency | 20,359 ms | 36,141 ms | +15,782 ms |
| Avg Tokens | 7,474.5 | 26,645.5 | +19,171.0 |

Human Calibration 평균은 Single-Agent RAG 4.0187, Multi-Agent 4.0625로 차이가 0.0438점이었다.
Pairwise에서는 Single-Agent RAG가 7:1로 앞섰지만 position bias가 30.77%였다. 현재 표본은
멀티에이전트 분해의 품질 우위를 안정적으로 뒷받침하지 않는다.

## 9. LLM Judge 결과

Pointwise Judge는 Multi-Agent를 높게 평가했지만 Human Calibration에서 아키텍처별 편향이
확인됐다. Human/Judge MAE는 0.5306이고 Pearson 상관계수는 -0.0890이다. Judge 점수는 보조
지표로만 사용한다.

## 10. Latency / Token / Cost

Multi-Agent 실측 P50/P95는 28,047/31,281ms이고 평균 토큰은 26,096.2/run이다. 승인된 가격
참조가 없어 비용 금액은 산출하지 않았다. 이미 완료한 Phase 5~8 외에 Phase 9~11에서는 신규
외부 LLM 호출이 없었다.

## 11. 실패 Case

실-provider Multi-Agent에서 `SQ-CONFLICT-001`, `SQ-CONFLICT-002`가 계획 없이 종료됐다.
두 건 모두 fallback이 안전한 계획을 만들 수 없어 fail-closed한 가용성 실패이며 unsafe plan과
critical failure는 0건이다. Phase 9 실패 주입 10건도 전부 안전 종료했다.

## 12. 발견된 결함

- D-1: 동일 입력의 LLM 출력 재현성 부족
- D-2: 최초 서비스 결함 판정을 운영 카탈로그 재현 후 테스트 하네스 문제로 정정
- D-3: advisory code가 계획에 반영되지 않는 품질 문제
- D-4: 기본 설정에서 LLM multi-agent가 비활성인 구성 정보
- D-5: Feasibility non-READY가 전체 경로를 막는 가용성 문제

배포 차단 수준의 안전 결함은 발견되지 않았다.

## 13. 한계

실-provider 표본 14건, 아키텍처 비교 28 run씩, Human Calibration 24건으로 표본이 작다.
생성과 Judge가 같은 모델 계열이며 사람 평가는 최종 합의 점수만 남아 평가자 간 일치도를 계산할
수 없다. HTTP·DB·인증 통합 장애는 이번 그래프 평가 범위가 아니다.

## 14. 개선 방향

1. D-5 readiness gate의 제품 의도를 PM·개발리드가 확정한다.
2. Judge의 consistency, explanation quality, groundedness 앵커를 사람 기준으로 보정한다.
3. 운영 카탈로그 구성과 같은 평가 pool로 50~100건을 재평가한다.
4. 다음 Human Calibration에서는 평가자별 원점수를 보존한다.

## Multi-Agent 적용 타당성 판단

결정적 안전 게이트와 역할 분리의 구현 타당성은 확인됐다. 그러나 현재 결과에서는 Multi-Agent가
Single-Agent RAG보다 안전하거나 상충 조건을 더 잘 해결하지 않았고, workflow completion은 낮으며
토큰과 지연은 크게 증가했다. Human Calibration의 품질 차이도 0.0438점에 그쳤다.

따라서 **현재 표본은 Multi-Agent를 기본 아키텍처로 선택할 비용 대비 우위를 입증하지 못했다.**
Single-Agent RAG가 신뢰성·비용·사람 평가 정합성에서 더 균형적이다. Multi-Agent를 유지한다면
D-5를 정리하고 더 큰 독립 Human Calibration에서 유의미한 품질 향상을 확인하는 조건이 필요하다.

## 산출물

필수 7종:

- `results/evaluation_summary.json`
- `results/evaluation_cases.csv`
- `results/retrieval_metrics.json`
- `results/agent_metrics.json`
- `results/architecture_comparison.csv`
- `results/latency_metrics.json`
- `results/failed_cases.json`

보조 산출물은 `results/category_metrics.csv`, 무결성 기록은 `results/phase11_manifest.json`이다.
