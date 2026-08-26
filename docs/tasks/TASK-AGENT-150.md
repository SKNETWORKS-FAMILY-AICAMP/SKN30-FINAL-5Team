# TASK-AGENT-150: Qdrant index 및 V3 staging evidence 수집

- 현재 상태: `APPROVED_FOR_STAGING_EVIDENCE`
- 우선순위: `P1`
- GitHub issue: `#150`
- Primary owner: 백엔드·데이터 개발팀장
- Reviewers: 백엔드 owner, AI/data lead, PM, 외부 도메인 검수자
- 관련 요구사항: `F002`, `F029`, `POL-008`, `NFR-003`, `NFR-005`, `NFR-006`
- 관련 ADR: `ADR-0013`, `ADR-0014`
- 목표 브랜치: 이슈 전용 branch/worktree 또는 비식별 evidence PR
- 승인자 역할: 백엔드·데이터 개발팀장
- 승인일: 2026-08-26

## 배경과 사용자 가치

V3 staging DEMO composition과 Qdrant adapter는 구현됐지만 실제 Qdrant index build, OpenAI staging
호출, latency/cost/fallback/safety evidence와 인간 승인은 수집되지 않았다. production flag를
변경하지 않고 승인 가능한 staging evidence를 만들어 구현 완료와 운영 승격을 명확히 분리한다.

이 승인은 staging evidence 수집만 허용하며 production promotion을 승인하지 않는다.

## 포함 범위

- LLM provider/model allowlist 승인 기록
- embedding provider/model/version/dimension/metric 승인 기록
- ACTIVE V2 catalog UUID 기반 immutable Qdrant collection build
- point count, build hash, version 검증과 atomic alias 전환
- PostgreSQL canonical re-read 확인
- Qdrant timeout, unavailable, stale version, missing point의 deterministic fallback 확인
- staging-only one-shot OpenAI shadow 실행
- provider call count, latency, token, cost, timeout, fallback과 safety hard gate 증적
- privacy allowlist 검사
- promotion evaluator 실행과 human approval 대기 상태 기록

## 제외 범위

- production V3 활성화
- 실제 사용자 데이터 shadow
- production DB와 production Qdrant
- prompt, chain-of-thought, provider 원문 응답과 원문 오류 저장
- 직접 식별자, raw check-in, health 또는 wearable 데이터 저장
- Qdrant를 PostgreSQL source of truth 대신 사용하는 변경

## 인수 조건

1. provider/model/embedding 계약은 현재 공식 provider 문서와 승인 기록에 근거한다.
2. model code와 allowlist는 exact match로 검증한다.
3. Qdrant build 입력은 PostgreSQL ACTIVE V2 catalog의 승인 UUID로 제한한다.
4. collection은 immutable하고 검증 완료 전 alias를 전환하지 않는다.
5. point count, build hash와 catalog/embedding/index version이 일치한다.
6. 검색 결과는 PostgreSQL canonical re-read를 통과해야 한다.
7. Qdrant 실패 시 deterministic fallback을 사용하고 PostgreSQL 실패를 Qdrant로 우회하지 않는다.
8. Safety veto 입력은 Qdrant와 LLM 호출 전에 종료된다.
9. evidence에 금지된 개인정보·건강정보·provider 원문이 없다.
10. 실제 call count, latency, token, cost, fallback과 safety 결과를 기록한다.
11. human approval 전에는 `READY_FOR_HUMAN_APPROVAL`을 production 승인으로 해석하지 않는다.
12. `V3_PRODUCTION_PROMOTION_APPROVED=false`를 유지한다.

## 변경 예상 파일

- 승인된 provider/embedding 계약 task 또는 ADR 증적
- `outputs/v3-shadow/<run_id>`의 ignored local evidence
- 필요 시 비식별 summary/manifest 또는 runbook 보완
- 이 task 문서의 실제 검증 결과

실제 credential, raw provider output과 staging secret은 커밋하지 않는다.

## API 영향

공개 API 변경 없음. staging DEMO와 shadow 경계만 사용하며 LEGACY production 응답을 변경하지 않는다.

## DB·마이그레이션 영향

새 migration 없음. PostgreSQL은 canonical exercise와 V3 persistence source of truth로 유지한다.
staging 전용 DB만 사용한다.

## 안전·개인정보·보안 영향

- Agent input은 normalized identifier-free 값으로 제한한다.
- prompt, chain-of-thought, raw provider payload와 exception text를 저장하지 않는다.
- token, API key와 endpoint credential은 process secret으로만 주입한다.
- Safety veto는 Coordinator, LLM, Qdrant 또는 fallback이 변경할 수 없다.
- callbacks/tracing을 통해 건강정보가 외부로 전송되지 않게 한다.

## 선행 관계와 차단 요소

- `#148`에서 ACTIVE V2 catalog의 실제 PostgreSQL 검증이 완료돼야 한다.
- `#149` 또는 동등한 staging 실행 환경이 준비돼야 한다.
- provider/model, embedding 계약과 가격 근거가 승인돼야 한다.
- PM, backend owner와 외부 도메인 검수자의 production 승인은 이 task와 별도다.

## 테스트 계획

- Qdrant local/server integration test
- index build count/hash/version 검증
- timeout/unavailable/stale/missing-point fallback test
- PostgreSQL canonical re-read test
- V3 golden/safety/privacy/fallback test
- staging one-shot shadow execution
- promotion evaluator
- formatter, linter, mypy와 관련 전체 backend test

## 수동 확인

개발팀장은 기준 SHA, provider/model/embedding versions, call budget, collection/alias, point count,
build hash, report hash, record count, latency/cost/fallback/safety 결과를 기록한다. 실제 secret과 raw
provider payload는 기록하지 않는다.

## 알려진 제한과 후속 작업

- staging 성공은 임상 검증 또는 production 승인이 아니다.
- 실제 사용자 shadow는 승인 범위가 아니다.
- threshold 승인, PM·개발팀장·backend owner·외부 전문가 서명과 production composition/flag 변경은
  별도 수동 승인과 후속 PR이 필요하다.
