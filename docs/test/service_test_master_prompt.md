현재 프로젝트에 대해 배포 전 서비스 품질 평가 및 테스트를 수행한다.

이번 작업의 목적은 단순히 테스트 코드를 작성하는 것이 아니라,
현재 구현된 멀티에이전트 기반 개인 맞춤 운동 추천 서비스의 품질을
정량적/정성적으로 검증하고, 최종 테스트 결과 보고서에 활용할 수 있는
재현 가능한 평가 결과를 생성하는 것이다.

중요:
- 먼저 현재 Repository를 분석한 뒤 실제 구현을 기준으로 테스트를 설계할 것.
- 존재하지 않는 Agent, Tool, Vector DB, API 등을 임의로 가정하지 말 것.
- 테스트를 통과시키기 위해 기존 서비스 로직을 임의로 변경하지 말 것.
- 테스트 기준(Target)을 결과 확인 후 유리하게 변경하지 말 것.
- 테스트 과정에서 발견한 서비스 결함과 테스트 코드 결함을 구분할 것.
- 기존 서비스 코드 수정이 필요한 경우 바로 수정하지 말고 원인과 수정 필요성을 먼저 기록할 것.
- 모든 평가가 동일 입력에서 재실행 가능하도록 seed, dataset, prompt, model 설정을 최대한 고정할 것.
- API Key, LangSmith Key 등 Secret은 코드나 결과 파일에 기록하지 말 것.

==================================================
PHASE 0. 프로젝트 구조 분석
==================================================

먼저 다음 항목을 분석한다.

1. LangGraph Workflow
2. Agent 종류와 역할
3. 각 Agent Input / Output Schema
4. Graph State Schema
5. Coordinator 또는 최종 의사결정 Node
6. Vector DB / Retriever
7. Embedding Model
8. RAG 사용 위치
9. 사용 LLM
10. Prompt
11. Safety 관련 Rule
12. 운동 추천 생성 과정
13. API Endpoint
14. 기존 테스트 코드
15. LangSmith 사용 여부

우리 기획상 다음과 같은 역할이 존재할 수 있으나,
실제 코드에 존재하는지를 반드시 확인한다.

- Training Agent
- Recovery/Safety Agent 또는 각각의 Agent
- Feasibility Agent
- Coordinator

분석 후 다음 파일을 작성한다.

docs/test/TEST_SYSTEM_ANALYSIS.md

여기에는 실제 구현 구조와 이후 테스트 대상 범위를 정리한다.

이 단계에서는 테스트 구현을 시작하지 않는다.

==================================================
PHASE 1. Evaluation Dataset 구축
==================================================

서비스 품질 테스트를 위한 고정 Evaluation Dataset을 구축한다.

Dataset은 최소 다음 Category를 포함한다.

- simple
- moderate
- complex
- conflict
- safety_critical
- rag_retrieval
- missing_input
- invalid_input
- failure_case

각 Test Case에는 가능한 범위에서 다음 정보를 포함한다.

- case_id
- category
- description
- user_input
- expected_constraints
- prohibited_actions
- expected_agent_behavior
- expected_safety_result
- expected_relevant_documents
- notes

특히 conflict case에는 다음과 같은 상충 조건을 포함한다.

예:
- 근력 향상 목표
- 높은 피로
- 수면 부족
- 특정 부위 통증
- 운동 시간 부족
- 제한된 장비
- 특정 운동 선호

Safety Critical Case에서는 잘못된 추천이 단 한 건이라도 발생하면
명확하게 식별 가능하도록 구성한다.

우선 10~20개의 Smoke Evaluation Dataset을 만들고
테스트 인프라 검증 후 전체 Dataset을 50~100건 수준으로 확장할 수 있는
구조로 작성한다.

Dataset 위치 예시:

tests/evaluation/datasets/
    smoke_cases.json
    evaluation_cases.json
    retrieval_cases.json

==================================================
PHASE 2. Deterministic Evaluation
==================================================

LLM Judge를 사용하기 전에 코드로 명확하게 판단 가능한 항목을 테스트한다.

다음 항목을 우선 검증한다.

1. Structured Output Schema Validation
2. 사용자 운동 가능 시간 초과 여부
3. 사용 불가능한 장비를 요구하는 운동 포함 여부
4. 제한/금기 운동 포함 여부
5. 통증 부위와 운동 추천 충돌
6. Safety BLOCKED 상태 무시 여부
7. 필수 입력 누락 처리
8. 비정상 입력 처리
9. Agent 간 State 정보 유실
10. LangGraph 정상 종료 여부
11. Graph 무한 반복 방지
12. Agent Exception 발생 시 처리

가능한 테스트는 pytest 기반으로 구현한다.

결과는 단순 PASS/FAIL뿐 아니라
실패 이유를 구조화하여 저장한다.

==================================================
PHASE 3. Vector Search / RAG Evaluation
==================================================

Retriever 자체와 최종 Generation을 분리하여 평가한다.

Retriever 평가 지표:

- Recall@1
- Recall@3
- Recall@5
- MRR
- Metadata Filter Accuracy

각 Retrieval Test Case에는 Ground Truth Document ID 또는
정답 Exercise ID를 지정할 수 있도록 한다.

예:

Query:
"덤벨만 이용해서 할 수 있는 가슴 운동"

Ground Truth:
관련 운동 Document ID

Retriever 평가 시 LLM 결과를 사용하지 말고
검색 결과만 독립적으로 평가한다.

결과 파일:

results/retrieval_metrics.json
results/retrieval_cases.csv

Generation/RAG 평가에서는
Retrieved Context를 최종 답변이 제대로 사용하는지 별도로 평가한다.

==================================================
PHASE 4. Multi-Agent Evaluation
==================================================

LangSmith Trace 또는 내부 Trace를 활용하여
멀티에이전트 Workflow를 평가한다.

다음 지표를 수집한다.

- Agent Invocation Accuracy
- Agent Role Consistency
- State Consistency
- Workflow Completion Rate
- Coordinator Conflict Resolution Accuracy
- Safety Compliance Rate
- Structured Output Success Rate

특히 다음 Conflict를 테스트한다.

A.
Training: 운동 강도 상향
Recovery: 운동 강도 하향

B.
Training: 운동 수행 추천
Safety: 해당 운동 BLOCKED

C.
Training: 60분 운동
Feasibility: 사용자 가능 시간 20분

D.
사용자 선호 운동
vs
통증/안전 제한

실제 서비스가 정의한 우선순위가 있다면
그 우선순위를 Ground Truth Rule로 사용한다.

Safety 관련 Rule은 LLM Judge가 아니라
가능한 범위에서 deterministic evaluation을 우선 사용한다.

==================================================
PHASE 5. LLM-as-a-Judge Evaluation
==================================================

정답을 Rule로 판정하기 어려운 최종 추천 품질에 대해서만
LLM-as-a-Judge를 사용한다.

평가 항목:

1. Personalization
2. Feasibility
3. Consistency
4. Explanation Quality
5. Groundedness / Faithfulness
6. Overall Recommendation Quality

각 항목은 1~5점으로 평가한다.

Judge에게는 반드시 평가 Rubric을 제공한다.

예:

5점:
사용자의 모든 핵심 조건을 정확하게 반영하며
추천과 설명 사이에 모순이 없고 실제 수행 가능함.

3점:
대부분 적절하지만 일부 조건을 누락하거나
조정 근거가 충분하지 않음.

1점:
사용자의 핵심 조건을 무시하거나
실제 수행하기 어려운 추천을 제공함.

Safety violation은 높은 Judge 점수와 관계없이 FAIL 처리한다.

Judge Prompt와 Judge Model 정보도 저장하여
평가를 재현할 수 있도록 한다.

==================================================
PHASE 6. Single Agent vs Multi-Agent 비교 실험
==================================================

이번 프로젝트에서 멀티에이전트 구조의 적용 타당성을 검증하기 위한
핵심 실험이다.

가능하면 아래 3개 Architecture를 비교한다.

A. Single LLM
B. Single Agent + RAG/Tools
C. 현재 Multi-Agent + RAG/Tools

단, A/B/C 비교에서 가능한 한 다음 조건을 동일하게 유지한다.

- LLM Model
- Temperature
- 사용자 입력
- Evaluation Dataset
- 운동 데이터
- Vector DB
- Embedding
- Tool 접근 범위
- Output Schema

즉 멀티에이전트에만 더 많은 정보를 제공해서는 안 된다.

핵심은 Architecture 차이의 효과를 측정하는 것이다.

평가 지표:

- Constraint Satisfaction Rate
- Safety Compliance Rate
- Complex Case Accuracy
- Conflict Resolution Accuracy
- Personalization Judge Score
- Feasibility Judge Score
- Overall Judge Score
- Workflow Success Rate
- P50 Latency
- P95 Latency
- Average Token Usage
- LLM/API Call Count
- 추정 API Cost

Simple / Moderate / Complex / Conflict / Safety Critical 별로
결과를 분리하여 비교한다.

특히 다음 가설을 검증한다.

"단순 운동 추천에서는 Single Agent와 Multi-Agent의 품질 차이가
크지 않을 수 있으나, 복수 조건이 동시에 존재하거나 서로 충돌하는
상황에서는 역할별 판단과 Coordinator를 사용하는 Multi-Agent가
조건 충족률, 안전성 및 일관성 측면에서 우수할 것이다."

가설에 맞지 않는 결과가 나오더라도 결과를 수정하거나 제외하지 말고
그대로 기록하고 원인을 분석한다.

==================================================
PHASE 7. Pairwise LLM Judge
==================================================

Single Agent와 Multi-Agent의 최종 응답을 Pairwise 방식으로 비교한다.

Judge에게 어떤 응답이 Single인지 Multi인지 알려주지 않는다.

평가 순서 편향을 방지하기 위해
A/B 응답 위치를 가능한 범위에서 Randomize한다.

결과:

- Single Win
- Tie
- Multi Win

으로 집계한다.

가능하다면 동일 Case를 순서를 바꾸어 재평가하여
Position Bias 여부도 확인한다.

==================================================
PHASE 8. LangSmith
==================================================

LangSmith가 프로젝트에 사용 가능한 상태라면 다음을 구성한다.

- Trace
- Dataset
- Experiment
- Evaluator

각 Test Run에는 식별 가능한 Experiment Name을 지정한다.

예:

baseline-single-agent-v1
multi-agent-v1
multi-agent-v2

Trace에서 최소한 다음을 확인할 수 있어야 한다.

- Agent Input
- Agent Output
- State
- Retriever 결과
- Coordinator 결과
- Token Usage
- Latency
- Error
- Retry

LangSmith가 설정되어 있지 않다면
Secret을 임의로 생성하거나 하드코딩하지 말고
필요한 환경변수와 설정 방법만 문서화한다.

LangSmith 연결이 없어도 로컬 Evaluation은 수행 가능하도록 만든다.

==================================================
PHASE 9. Performance / Failure Evaluation
==================================================

평균 응답시간뿐 아니라 다음을 측정한다.

- P50 Latency
- P95 Latency
- 평균 Token Usage
- LLM Call Count
- Workflow Completion Rate
- Parsing Error Rate
- Node Error Rate

Failure Case도 테스트한다.

예:

- Retriever 검색 결과 없음
- LLM Timeout
- Structured Output Parsing Error
- Agent Exception
- Empty Input
- Invalid Input
- Graph Loop
- 외부 API Failure

이때 시스템이 좋은 답변을 생성하는지보다
안전하게 종료되거나 Fallback하는지를 평가한다.

==================================================
PHASE 10. Human Calibration
==================================================

LLM Judge가 항상 정확하다고 가정하지 않는다.

대표 Test Case 20~30건을 별도로 추출할 수 있도록 하고,
Human Evaluation 결과를 나중에 입력할 수 있는 형태를 만든다.

다음 비교가 가능해야 한다.

case_id
human_score
judge_score
score_difference

이를 통해 Judge Prompt의 신뢰성을 평가할 수 있게 한다.

Human Label이 현재 없다면 임의로 생성하지 않는다.

==================================================
PHASE 11. 결과 산출
==================================================

모든 테스트가 완료되면 최소 다음 결과물을 만든다.

results/
    evaluation_summary.json
    evaluation_cases.csv
    retrieval_metrics.json
    agent_metrics.json
    architecture_comparison.csv
    latency_metrics.json
    failed_cases.json

docs/test/
    TEST_SYSTEM_ANALYSIS.md
    TEST_PLAN.md
    TEST_RESULTS.md

TEST_RESULTS.md에는 다음을 반드시 포함한다.

1. 테스트 환경
2. Dataset 구성
3. 사용 모델
4. 평가 방법
5. Deterministic Test 결과
6. Retriever 성능
7. Multi-Agent 품질
8. Single vs Multi 비교
9. LLM Judge 결과
10. Latency / Token / Cost
11. 실패 Case
12. 발견된 결함
13. 한계
14. 개선 방향

Single vs Multi 결과는 다음과 같은 표로 정리한다.

Metric | Single Agent | Multi-Agent | Difference
Constraint Satisfaction | | |
Safety Compliance | | |
Conflict Resolution | | |
Judge Score | | |
P95 Latency | | |
Avg Tokens | | |

또한 Category별 결과도 별도 출력한다.

Simple
Moderate
Complex
Conflict
Safety Critical

==================================================
실행 방식
==================================================

처음부터 전체 평가를 실행하지 않는다.

1. Repository 분석
2. 테스트 설계
3. Smoke Dataset 5~10건 실행
4. 테스트 Harness 오류 수정
5. 10~20건 Pilot Evaluation
6. 결과 검토
7. 전체 Evaluation Dataset 실행

순서로 진행한다.

LLM API 비용이 발생하는 Full Evaluation을 실행하기 전에는
예상 호출 수 및 예상 비용을 계산해서 알려준다.

단순 pytest / deterministic test는 바로 실행해도 된다.

==================================================
최종 보고 시
==================================================

작업 완료 후 단순히 "테스트 완료"라고 하지 말고 다음을 보고한다.

- 생성/수정한 파일
- 실행한 명령어
- 실행한 테스트 수
- PASS / FAIL
- 주요 Metric
- 실패한 Case
- 발견된 서비스 결함
- 테스트 자체의 한계
- 아직 실행하지 못한 항목
- 추가로 필요한 환경변수/API Key
- Full Evaluation 예상 비용

그리고 현재 결과로
Multi-Agent 구조의 적용 타당성이 실제로 확인되었는지도
결과에 기반하여 판단한다.

결과가 Multi-Agent의 우위를 뒷받침하지 않을 경우에도
그 사실을 숨기지 말고 원인을 분석한다.

특히 Single vs Multi는 별도 작업으로 떼는 게 좋습니다

이 실험은 Agent가 편의상 Single Agent를 너무 단순하게 구현해버리면 결과가 무의미해집니다. 그래서 다음 지시를 별도로 주는 것을 권합니다.

Single Agent baseline을 일부러 약하게 만들지 마세요. Multi-Agent와 동일한 LLM, Vector DB, 데이터, Tool, 사용자 정보를 사용할 수 있도록 하고, 하나의 Agent가 Training/Recovery/Safety/Feasibility 판단을 하나의 Context 안에서 수행하도록 구성하세요. 비교 대상의 핵심 차이는 정보 접근 가능성이나 모델 성능이 아니라 의사결정 Architecture가 되어야 합니다.

이 한 문장이 상당히 중요합니다.

그리고 기존 멀티에이전트 서비스를 Single Agent 형태로 영구 수정할 필요도 없습니다. 테스트용 baseline runner를 별도로 만드는 것이 좋습니다.

예를 들면 구조를 이런 식으로 두는 편이 깔끔합니다.

tests/
└── evaluation/
    ├── datasets/
    │   ├── smoke_cases.json
    │   ├── evaluation_cases.json
    │   └── retrieval_cases.json
    │
    ├── evaluators/
    │   ├── constraint_evaluator.py
    │   ├── safety_evaluator.py
    │   ├── retrieval_evaluator.py
    │   ├── judge_evaluator.py
    │   └── latency_evaluator.py
    │
    ├── runners/
    │   ├── run_single_llm.py
    │   ├── run_single_agent.py
    │   ├── run_multi_agent.py
    │   └── run_pairwise.py
    │
    ├── test_agent_behavior.py
    ├── test_state.py
    ├── test_safety.py
    └── test_retrieval.py

results/
├── raw/
├── single_agent/
├── multi_agent/
└── comparison/

이렇게 하면 기존 서비스 코드에 손을 많이 대지 않고도 동일 Dataset → 서로 다른 Runner → 동일 Evaluator라는 상당히 깔끔한 실험 구조가 나옵니다.

가장 중요한 원칙은 **Runner는 다르지만 Evaluator는 동일해야 한다**는 것입니다. 그래야 Single Agent와 Multi-Agent 비교 결과를 보고서에서 신뢰성 있게 제시할 수 있습니다.