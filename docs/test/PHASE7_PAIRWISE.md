# PHASE 7 Pairwise Judge 결과

- 실행일: 2026-09-11
- 계획 생성·심사 모델: `OPENAI:gpt-5.6-terra`
- 산출물: `results/pairwise/payloads.json`, `results/pairwise/pairwise.json`
- Judge 호출: 76회
- 각 pair의 순서: 2회(서로 반대로 제시)

## 결론

Single Agent + RAG는 Single LLM에 11:1로 우세했고, Multi-Agent는 Single LLM에 10:1로
우세했다. 가장 중요한 B 대 C 비교에서는 Single Agent + RAG가 7:1로 우세했지만, 순서 반전
일치율이 61.54%에 그치고 position bias가 30.77%여서 강한 결론으로 일반화할 수 없다.

| 비교 | 판정 가능 | 제외 | 왼쪽 승 | 오른쪽 승 | 불일치 | 순서 일치율 | Position bias |
|---|---:|---:|---:|---:|---:|---:|---:|
| Single LLM vs Single Agent + RAG | 13 | 1 | 1 | 11 | 1 | 92.31% | 0.00% |
| Single LLM vs Multi-Agent | 12 | 2 | 1 | 10 | 1 | 91.67% | 0.00% |
| Single Agent + RAG vs Multi-Agent | 13 | 1 | 7 | 1 | 5 | 61.54% | 30.77% |

무계획 pair는 무승부로 돌리지 않고 판정에서 제외했다. 두 순서 중 하나가 tie이거나 서로 다른
계획을 선택하면 `DISAGREED`로 보존했다.

## 블라인딩과 편향 통제

- Judge에게 아키텍처 이름을 제공하지 않았다.
- `advisory_codes`를 제외했고 아키텍처를 드러낼 수 있는 decision code 20개를 redact했다.
- case ID 해시로 첫 제시 위치를 재현 가능하게 정했다.
- 모든 pair를 역순으로 한 번 더 평가했다.
- 모의 `AlwaysFirstPairwiseJudge`가 bias 1.0을 검출하는지 단위 테스트로 확인했다.

## 해석

PHASE 6의 pointwise 평균은 Multi-Agent 4.40, Single Agent + RAG 4.08이었지만, pairwise에서는
Single Agent + RAG 쪽으로 기울었다. 동시에 B 대 C에서 5/13이 불일치했고 4/13이 위치를 따라가
두 방식의 품질 차이가 심사 안정성보다 크다고 보기 어렵다. 현재 표본으로는 RAG의 가치는 지지되지만
멀티에이전트 분해의 우월성은 확인되지 않았다.

## 재현

저장된 `payloads.json`으로 judge-only 재실행이 가능하므로 그래프와 provider 계획 생성을 다시
수행할 필요가 없다. 원본 결과는 수정하지 않았으며, 상세 case·rubric 집계는
`results/pairwise/pairwise.json`에 남아 있다.

## 한계

- smoke planning case 14건의 소표본이다.
- 생성과 심사에 같은 모델 계열을 사용해 self-preference 가능성이 있다.
- pairwise 결과는 안전성 검증을 대체하지 않는다. 안전성은 결정적 validator 결과를 따른다.
