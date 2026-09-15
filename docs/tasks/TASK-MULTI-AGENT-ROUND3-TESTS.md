# TASK-MULTI-AGENT-ROUND3-TESTS

## 목적

1·2차 평가에서 확인된 안전성과 계획 전달 성공을 보존하면서, Multi-Agent의 지연과 확률적 실패를
공정하게 다시 측정할 수 있는 Round 3 평가 기반을 만든다. 이 작업은 평가 코드와 문서만 변경하며
운영 그래프, 안전 규칙, 공개 API 및 DB 계약은 변경하지 않는다.

## 배경

- Round 2 공식 판정은 안전·전달 관련 4개 기준 통과, 지연·complex 계획률 2개 기준 미달이다.
- Single-Agent baseline은 거절 상태를 표현할 수 없어 기존 `llm_plan_rate`만으로는 공정한 비교가
  어렵다.
- ADR-0024 뒤에도 Coordinator domain-invalid가 5/40 남았지만 실패 역할·단계를 집계하는 공식
  지표가 없다.
- Multi-Agent P95가 30초 기준을 넘었지만 역할·phase별 P50/P95가 비교 산출물에 포함되지 않는다.
- category별 표본이 작고 실행 간 변동이 커 점추정치만으로 구조 우위를 판정할 수 없다.

## 변경 범위

1. 기존 결과 분류를 유지하면서 모델 결과와 최종 전달 결과를 분리한다.
2. 실패를 entry, specialist 역할, Coordinator initial/repair, compiler, integrity, fallback 단계로
   분류한다.
3. 역할·phase별 호출 수, 실패 수, P50/P95 지연과 token을 비교 보고서에 추가한다.
4. 비율에 Wilson 95% 신뢰구간을 제공하고 동일 순서의 반복 run을 paired 비교한다.
5. category 표적 선택과 실제 선택 case manifest를 산출물에 고정한다.
6. 실제 provider 호출 전 실행할 Round 3 사전 등록 기준을 문서화한다.

## 수용 기준

- 기존 Round 2 JSON 필드는 삭제하거나 의미를 변경하지 않는다.
- 모든 architecture에 동일한 분류 함수를 적용한다.
- `LLM_AGENT_DOMAIN_INVALID`는 invocation audit가 있으면 역할과 phase까지 식별한다.
- fallback 전달과 모델 직접 통과를 별도 필드로 보고한다.
- 호출 지연은 graph의 기존 `InvocationAudit`만 사용하며 새 사용자 데이터나 prompt를 저장하지 않는다.
- 비교 대상의 case 순서가 다르면 paired 결과를 만들지 않고 명시적으로 실패한다.
- 관련 evaluation unit test, Ruff가 통과한다.

## Round 3 실행 게이트

1. 무료 scripted 회귀와 평가 하네스 테스트
2. conflict/complex 표적 dry-run 및 호출량 manifest 검토
3. 오너가 조건부 specialist 호출 정책을 ADR로 승인한 경우에만 새 architecture variant 추가
4. 비식별 입력, 모델, 반복 수, 최대 호출 수와 비용 상한 승인 후 유료 pilot
5. unsafe/critical/privacy 위반이 1건이라도 있으면 즉시 중단

## 사전 등록 비교안

- 주 비교: Single-Agent+RAG 대 현재 Multi-Agent+RAG
- 대상: held-out의 conflict/complex 20~30건
- 반복: architecture별 최소 3회, 권장 5회
- 필수 지표: safety, plan delivery, 모델 직접 통과, normalized failure, fallback, 역할별 지연,
  전체 P95, 호출 수, token
- 판정: safety 1.000 및 critical 0을 전제로 Multi P95 30초 이하, paired 직접 통과율이 Single RAG
  이상일 때만 다음 승격 검토로 이동
- Judge/Human 점수는 독립 다수 평가자와 평가자 간 일치도가 확보되기 전까지 진단용으로만 사용

현재 60건 확대 dataset에서 conflict/complex planning 대상은 28건이다. B/C를 3회 반복하고 Judge를
끄면 정상 경로 기준 provider 호출 예상은 420회다. retry·repair 여유를 포함한 `--max-calls`와 실제
비용 상한은 유료 실행 승인 전에 별도로 고정한다. 재현용 dry-run은 다음과 같다.

```powershell
python -m backend.tests.evaluation.comparison_cli --dry-run `
  --dataset expanded_heldout_cases --categories conflict complex `
  --architectures SINGLE_AGENT_RAG MULTI_AGENT --repeats 3 --no-judge
```

## 위험과 제한

- 조건부 Recovery/Feasibility 호출은 ADR-0015의 역할 구조 및 제품 동작에 영향을 줄 수 있으므로
  이 작업에서 임의 구현하지 않는다.
- 과거 산출물은 새 진단 필드를 갖지 않으므로 재생성 없이 소급 계산할 수 있는 범위만 분석한다.
- 실제 provider 반복 실행은 비용을 발생시키므로 이 작업의 자동 검증에 포함하지 않는다.

## 실행 결과

2026-09-15 오너 승인으로 conflict/complex 28건을 B/C 각각 3회, Judge 제외로 실행했다. 실제
provider 호출은 417회, 공식 가격 기준 비용은 $9.5333이었다. Safety·Plan Delivery·Workflow는
두 architecture 모두 1.000이고 critical failure는 0이었다. Multi-Agent P95는 40.734초,
모델 직접 계획률은 B 0.9643 대 C 0.8690이었다. 공통 fallback에서 금지 장비 위반 MAJOR 결함을
발견했으며 상세 판정과 후속 조치는 `docs/test/ROUND3_RESULTS.md`를 따른다.
