# 인계 문서 — 서비스 품질 평가 (2026-09-11)

다른 담당자가 이어받기 위한 문서다. 결론, 남은 작업, 그리고 **이어받는 사람이 모르면 틀리게
될 사실**을 담는다. 세부 수치는 원 문서를 가리킨다.

- 브랜치: `fix/v3-round2-quality-improvement` (base `6deb151`, `develop`에서 분기)
- 커밋 27개, push 안 됨
- 상태: **게이트 1~7 완료, 게이트 8(최종 판정·보고) 미착수**

---

## 1. 한 문단 요약

배포 전 서비스 품질 평가를 마스터 명세(`service_test_master_prompt.md`)에 따라 1차(PHASE 0~11)와
2차(held-out) 두 라운드로 수행했다. **안전성은 두 라운드 모두 완전히 유지됐다**(safety 1.000,
critical 0). **Multi-Agent가 Single-Agent + RAG보다 낫다는 가설은 입증되지 않았다** — 1차에서
입증 실패했고, 개선(ADR-0021, ADR-0022) 후 held-out 재측정에서도 사전 등록 기준 2개가 미달했다.
다만 조사 과정에서 **측정 지표 자체가 교란돼 있었다**는 사실이 두 건 드러났고(9~11절), 이는
"Multi-Agent가 나쁘다"가 아니라 **"지금까지의 비교로는 판정할 수 없다"** 쪽을 가리킨다.

---

## 2. 반드시 지켜야 할 규칙

이어받는 사람이 어길 가능성이 높은 순서로 적는다.

1. **사전 등록 기준을 결과를 본 뒤에 바꾸지 않는다.** `ROUND2_IMPROVEMENT_PLAN` 3절의 7개
   기준은 고정이다. 새로 만든 지표(10절 분해, 11절 calibration)는 **해석용 보조**이지
   판정 기준이 아니다. 유리한 지표로 갈아타면 이 평가 전체가 무의미해진다.
2. **Secret을 코드·결과 파일·로그·콘솔에 남기지 않는다.** 유료 실행은 AWS Secrets Manager에서
   인라인으로 읽는다. 길이만 출력하고 값은 출력하지 않는다.
3. **테스트를 통과시키려고 서비스 로직을 고치지 않는다.** 원인과 필요성을 먼저 문서에 기록한다.
   실제로 서비스 코드를 고친 세 번(ADR-0021, ADR-0022, D-7) 모두 기록 → 승인 → 수정
   순서를 밟았다(9절).
4. **서비스 결함과 테스트 결함을 구분한다.** 1차의 D-2는 서비스 결함으로 보고했다가 하네스
   결함으로 정정한 사례다. 정정 기록을 지우지 말 것.
5. **없는 Agent/Tool/Vector DB/API를 가정하지 않는다.**
6. `backend/app/domain/agents/**`는 AI/데이터 리드 소유이고 안전 인접 변경은 PM·도메인 리뷰가
   필요하다(AGENTS.md 3절). ADR 없이 고치지 않는다.
7. **최종 요약은 한국어로 작성한다.**

---

## 3. 결론 (사전 등록 기준 판정)

`ROUND2_IMPROVEMENT_PLAN` 3절 기준, held-out 재측정(`results/round2/heldout_adr22/`) 결과.

| 지표 | 기준 | 실측 | 판정 |
|---|---:|---:|:--:|
| Safety golden pass rate | 1.000 | 1.000 (33/33) | 통과 |
| Critical / unsafe plan | 0건 | 0건 | 통과 |
| 실-provider workflow completion | ≥ 0.950 | 1.000 | 통과 |
| v1 Multi 대비 평균 total token | ≥ 25% 감소 | 26.9786% 감소 | 통과 |
| Multi − Single RAG **Human** mean | ≥ +0.20 | **미측정** | **미판정** |
| Multi P95 latency | ≤ 30초 | **43.093초** | **미달** |
| conflict/complex plan rate | ≥ Single RAG | **complex 0.667 대 0.944** | **미달** |

**판정: "Multi-Agent가 더 유효하다"는 결론을 내리지 않는다.** `ROUND2_IMPROVEMENT_PLAN` 6절의
**"Single RAG가 동등 이상"** 분기다.

Human mean은 오너가 "과정을 직접 관찰해 평가했으므로 독립 human 평가 불필요"로 판단했다.
**그렇더라도 미판정으로 남겨 두었다** — 결과를 본 뒤 기준을 없애는 것이 되기 때문이다.

---

## 4. 그런데 판정을 그대로 읽으면 안 되는 이유 (핵심)

미달한 두 기준 중 **plan rate 쪽은 지표가 교란돼 있었다.**

### 4.1 두 아키텍처의 출력 계약이 비대칭이다 (9.4절)

| | 상태 필드 | 처방 최소 개수 |
|---|---|---|
| `SpecialistAgentProposal` (Multi-Agent) | `proposal_status_code`: READY / **NEEDS_INPUT** / FAILED | — |
| `SingleAgentPlanDraft` (baseline) | **없음** | `min_length=1` |

Single-Agent 프롬프트는 Training 프롬프트를 그대로 포함하므로 NEEDS_INPUT 지시 문장도 있지만,
**출력 스키마에 그것을 표현할 자리가 없다.** 계획을 내거나 스키마 검증에 실패하거나 둘 중
하나다.

따라서 `llm_plan_rate`는 "계획을 세울 수 있는가"와 **"거절할 수단이 있는가"를 함께 재고 있다.**
58 run에서 Training은 11회 거절(19%), baseline은 0회 — 거절할 수 없기 때문이다.

**분해 결과(10절, 2회차 실행):**

| | plan | declined | **rejected** (아키텍처 대칭) |
|---|---:|---:|---:|
| B. Single Agent + RAG | 0.8621 | 0.0000 | **0.1379** |
| C. Multi-Agent | 0.7241 | 0.2414 | **0.0345** |

계획을 시도한 run만 보면 게이트 거부율은 **C 1/22 (0.0455) 대 B 4/29 (0.1379)**.
**C가 계획을 내놓기로 한 경우, 그 계획은 B의 계획보다 게이트를 훨씬 잘 통과한다.**

### 4.2 Judge 평균도 교란돼 있었다 (11절)

아키텍처별 Judge 평균은 **fallback 빈도를 섞고 있다**(Judge는 blind 상태에서 템플릿과 모델
계획을 0.85점 차이로 구분하므로). 저작 계획만 비교하면:

| | 전체 평균 | 저작 계획만 |
|---|---:|---:|
| B | 3.6322 | **3.7267** |
| C | 3.5172 | **3.7222** |
| 차이 | −0.1150 | **−0.0045** |

짝지어 부호검정에서 C 대 B는 저작 계획 기준 **9 대 9, p = 1.0000**. Judge는 둘을 구분하지
못한다. (반면 retrieval 유무는 p < 0.001로 확실히 구분한다.)

### 4.3 그래서 무엇을 주장할 수 있고 없는가

**주장 가능**

- 안전성은 held-out에서도 완전히 유지된다.
- Judge는 retrieval의 가치를 확실히 구분한다(A 대 B/C, p < 0.001).
- C가 저작한 계획은 결정적 게이트를 B보다 잘 통과한다.

**주장 불가**

- "Multi-Agent가 더 유효하다" — 사전 등록 기준 미달.
- "거절 수단이 없었다면 C가 이겼을 것" — 관측되지 않은 반사실.
- "Judge가 B를 선호한다" — p = 1.0000.
- latency 미달은 교란과 무관하다. **P50 27.094초, P95 43.093초는 실측 그대로 기준 초과다.**

---

## 5. 실행 게이트 진행 현황

`ROUND2_IMPROVEMENT_PLAN` 5절 기준.

| # | 게이트 | 상태 |
|---|---|---|
| 1 | 계약·unit·privacy·golden/safety 테스트 | 완료 |
| 2 | 기존 20 case 오프라인 회귀 | 완료 |
| 3 | 실-provider smoke + LangSmith span | 완료 (ADR-0020) |
| 4 | 유료 pilot | 완료 (14/14) |
| 5 | held-out 전체 실행 | **완료 ×2** (수정 전·후) |
| 6 | 독립 blind Human 평가 | **오너 판단으로 생략** — 기준은 미판정 유지 |
| 7 | Judge calibration | 완료 (11절) |
| 8 | **성공 기준 판정과 최종 보고** | **미착수 ← 여기부터** |

---

## 6. 남은 작업

### 6.1 게이트 8 — 최종 보고서 (즉시 가능, 무료)

마스터 명세 `service_test_master_prompt.md` 440행이 `TEST_RESULTS.md`를 필수 산출물로 지정하고
**14개 필수 절 + Single vs Multi 비교표 + Category별 결과**를 요구한다(`TEST_PLAN.md` 430행).

현재 `TEST_RESULTS.md`는 **1차 결과만** 담고 있고 2차 결과는 `ROUND2_HELDOUT_RESULTS.md`에
분리돼 있다. 상단에 상호 참조 주석을 넣어 뒀다. 최종 보고서를 어느 파일에 쓸지는 결정이
필요하다 — 명세가 파일명을 지정하므로 **`TEST_RESULTS.md`를 확장하는 쪽을 권한다.**

보고서에 반드시 포함할 것: 4절의 교란 두 건. 이것 없이 "Multi-Agent 미달"만 적으면 **잘못된
후속 조치**(계획 능력을 고치라는 처방)로 이어진다.

### 6.2 Training 거절 사유 확인 (유료, 약 255 호출)

**가장 가치 높은 미해결 질문이다.** 현재까지 확인된 것:

- 계약 위반이 아니다 (`V3_TRAINING_PROPOSAL_INVALID` 0건, `V3_TRAINING_NOT_READY` 7건)
- payload 문제가 아니다 (Training만 전체 pool을 받는다)
- 입력이 부족한 것도 아니다 (실패 case 전부 WARMUP/MAIN/COOLDOWN 후보, CORE, 승인 volume 보유)
- **구조적 예측 인자가 없다** (SQ-HELD-009/010/011/012는 구조가 동일한데 009만 실패)

`decline_reason_codes`를 기록하도록 고쳐 뒀다(커밋 `1e660af`). **다음 유료 실행에서 Training이
어떤 조건을 들어 거절하는지 기록된다.** 그 데이터를 보기 전에 프롬프트를 고치지 말 것.

실행 명령:

```bash
# 시크릿은 Secrets Manager에서 인라인으로 읽고 파일에 쓰지 않는다
uv run python -u -m backend.tests.evaluation.comparison_cli --confirm-spend \
  --dataset heldout_cases --repeats 1 --max-calls 320 \
  --output-dir results/round2/heldout_reasons
```

### 6.3 미결 결정 사항 (오너 판단 필요)

| 항목 | 내용 |
|---|---|
| `approved_safe_alternative_ids` | 누가 산출하는가(Qdrant snapshot loader / 안전 규칙). 정해지기 전까지 `SAFETY_EXCLUDED_EXERCISE_INCLUDED`는 복구 불가(안전한 동작) |
| 표본 크기 | category당 n이 3~9라 기준 판정에 부족하다. `ROUND2_IMPROVEMENT_PLAN` 4절 권장값은 50~100 case |
| D-1 재현성 | "동일 입력 → 동일 출력"을 제품 요건으로 확정할지. 2차 범위 밖으로 보류 |
| PlanSpec 비중립성 | 출력 계약을 architecture-neutral하게 만들지. 4.1절 교란의 근본 원인 |

---

## 7. 이어받는 사람이 모르면 틀리는 것들

실제로 이 작업 중에 틀렸던 것들이다.

1. **배포 카탈로그는 `v2.0.7-final`이다. `v2.0.8`이 아니다.** `approvals.py`의 최신 승인
   항목을 배포본으로 가정해 한 번 틀렸다. 배포는 어떤 promotion 명령을 실행했는지로 정해지며
   `infra/deployment/README.md`가 v2.0.7만 문서화한다. `test_the_replay_uses_the_catalog_the_service_deploys`가
   재발을 막는다.

2. **가짜 테스트 더블이 결함을 숨긴다. 두 번 당했다.**
   - `test_v3_langgraph_repair.py`의 가짜 validator가 "repairable"을 그대로 돌려줘서, **repair
     노드가 프로덕션에서 도달 불가능하다는 사실을 숨겼다**(D-6). 배선과 분류기는 각각
     검증됐는데 **둘을 잇는 이음매를 함께 검증한 테스트가 없었다.**
   - specialist fake가 telemetry를 보고하지 않아 **과금된 호출이 0 토큰으로 집계되는 버그를
     숨겼다**(D-7).
   - 교훈: 실제 구현 두 개를 **함께** 통과시키는 테스트를 하나는 두어라.

3. **스크립트 provider로는 integrity validator 경로를 시험할 수 없다.** 잘못된 coordinator
   출력이 전부 구조화 출력 스키마 단계에서 거부된다(`LLM_AGENT_SCHEMA_INVALID`). repair
   도달성을 평가 하네스로 증명하려다 실패했고, unit 수준(실제 validator + 실제 routing, 빈
   context)에서 증명했다.

4. **fallback을 섞으면 상관계수 부호가 뒤집힌다.** FEASIBILITY 접지 검사에서 처음 +0.5152가
   나왔는데, 템플릿은 시간을 정확히 맞추며 점수가 낮고 모델 계획은 시간이 흔들리며 점수가
   높아서 생긴 Simpson's paradox였다. 저작 계획만으로 재계산한 값은 −0.0297이다.
   **아키텍처별 평균을 낼 때는 항상 fallback 포함 여부를 명시하라.**

5. **접미사 매칭으로 실패 코드를 분류하지 마라.** `V3_COMPILATION_FAILED`가 `_FAILED`로 끝나서
   "specialist 거절"로 분류됐다. compiler가 계획을 거부한 것이니 정반대다. `outcomes.py`는
   역할 코드를 enum에서 유도한다.

6. **실행 간 변동이 크다.** B의 conflict plan rate가 두 실행 사이에 0.800 → 0.400으로
   뒤집혔다(n=5에서 2건). **단일 실행으로 category별 기준을 판정하지 마라.** 두 실행 합산
   (58 run)은 B 0.879 대 C 0.741, conflict 0.600 동률, complex 0.944 대 0.667.

7. **유료 실행은 `python -u`로 돌려라.** 버퍼링되면 진행 상황이 안 보인다.

8. **1회차 held-out 산출물에는 실패 코드가 없다**(`CaseEvaluation.failure_codes`를 그 후에
   추가했다). 1회차 multi-agent 원인은 LangSmith trace에서 복원해 3절에 기록해 뒀다.
   **분해·calibration 분석은 2회차만 쓸 수 있다.**

---

## 8. 산출물 위치

### 문서 (`docs/test/`)

| 파일 | 내용 |
|---|---|
| `service_test_master_prompt.md` | 마스터 명세 (요구사항 원본) |
| `TEST_PLAN.md` | 테스트 계획 |
| `TEST_RESULTS.md` | **1차 결과** (명세가 지정한 필수 산출물명). D-1~D-5 결함 목록 12절 |
| `PHASE6_COMPARISON.md` | 1차 A/B/C 비교 |
| `PHASE7_PAIRWISE.md` | blind pairwise, position bias 30.77% |
| `PHASE8_LANGSMITH_LLM_SPAN.md` | LLM span opt-in (ADR-0020) |
| `PHASE9_PERFORMANCE_FAILURE.md` | 실패 주입 |
| `PHASE10_HUMAN_CALIBRATION.md` | 1차 human calibration (24건) |
| `PHASE11_FINAL_RESULTS.md` | 1차 최종 |
| `ROUND2_IMPROVEMENT_PLAN.md` | **2차 계획 + 사전 등록 기준 + 진행 현황** |
| `ROUND2_LOCAL_RESULTS.md` | 2차 오프라인 |
| `ROUND2_HELDOUT_RESULTS.md` | **2차 held-out 결과 11개 절. 가장 중요한 문서** |
| `HANDOFF.md` | 이 문서 |

`ROUND2_HELDOUT_RESULTS.md` 절 구성: 1~7 수정 전 실행 / 8 ADR-0022 재측정 /
9 Training READY 조사 / 10 plan rate 분해 / 11 Judge calibration.

### 결과 (`results/round2/`)

| 디렉터리 | 내용 |
|---|---|
| `heldout/` | 1차 held-out 유료 (256 호출). **실패 코드 없음** |
| `heldout_adr22/` | 2차 held-out 유료 (255 호출). **실패 코드 포함, 분석의 기준** |
| `judge_calibration/` | Judge calibration 산출물 |
| `offline/`, `offline_adr22/` | 무료 배관 점검 |

### ADR

- `0020-opt-in-langsmith-provider-tracing.md`
- `0021-v3-advisory-readiness-and-minimum-payload.md`
- `0022-repair-reachability-and-failure-code-separation.md`

---

## 9. 서비스 코드 변경 이력

평가 중 서비스 코드를 고친 것은 **세 번뿐이고 모두 ADR 또는 문서 기록을 선행**했다.

| 커밋 | 변경 | 근거 |
|---|---|---|
| `97e380f`, `2519a41` | advisory NEEDS_INPUT 허용, 역할별 최소 payload, `reasoning_effort=low` | ADR-0021 (D-5 대응) |
| `7ae59a6` | repair 도달 가능성 복구, specialist 실패 코드 3분리 | ADR-0022 (D-6) |
| `1e660af` | 실패·거절 분기 telemetry 보존, `decline_reason_codes` 기록 | D-7, 9.5~9.6절 |

**어느 것도 위반 판정 규칙이나 안전 경계를 넓히지 않았다.** ADR-0022는 repair 산출물이 같은
validator로 재검증되므로 "repair 없이도 통과했을 계획"만 통과시킨다.

---

## 10. 검증 상태

- `uv run python -m pytest backend/tests -q` → **2329 passed, 91 skipped**
  (skip은 전부 `TEST_DATABASE_URL` 미설정)
- `uv run ruff check backend` → 통과
- `uv run mypy backend/app` → 통과 (219 files)
- `uv run mypy backend/tests/evaluation` → **기존 오류 25건 잔존**. 이 작업에서 추가된 것은
  없으며, `production_catalog.py` 등 평가 하네스 파일에 원래 있던 것이다.

---

## 11. 다음 담당자에게 권하는 순서

1. `ROUND2_HELDOUT_RESULTS.md` 8~11절을 읽는다. 여기에 결론과 교란이 다 있다.
2. 게이트 8 최종 보고서를 쓴다(6.1절). **4절의 교란 두 건을 반드시 포함한다.**
3. 오너에게 6.3절 미결 사항을 올린다.
4. 예산이 허락하면 6.2절 유료 실행으로 Training 거절 사유를 확보한다. 이것이 "multi-agent
   단순화 또는 조건부 호출"(`ROUND2_IMPROVEMENT_PLAN` 6절)을 후속 ADR로 올릴지 판단하는
   마지막 근거다.
