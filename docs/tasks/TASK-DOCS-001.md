# TASK-DOCS-001: 개발 현황 및 계약 정합화

- 상태: `COMPLETE`
- GitHub issue: 미발급
- Primary owner: 개발 리드
- Reviewers: 백엔드 owner, 프론트엔드 owner, PM
- 관련 요구사항: `NFR-002`, `NFR-006`, MVP 기능 `F001`~`F011`, `F025`~`F029`
- 관련 ADR: ADR-0004, ADR-0007, ADR-0008, ADR-0009, ADR-0010, ADR-0011
- 목표 브랜치: `docs/development-contract-alignment`
- 기준 커밋: `bc5513123df3b608965a1143d4cfeb00fdbd6608`

## 배경과 사용자 가치

2026-08-13 기준 착수 문서와 초기 추적표가 이후 병합된 기능을 반영하지 못해, 이미 구현된 기능과
보류된 외부 연동을 구분하기 어렵다. 개발·검수 담당자가 실제 코드와 테스트를 기준으로 다음 작업의
우선순위를 결정할 수 있도록 현황과 추적 근거를 정합화한다.

## 포함 범위

- 백엔드 현황 문서를 2026-08-20 `develop` 기준으로 갱신
- MVP 요구사항 그룹의 API·DB, 코드, 테스트, 병합 PR 근거 연결
- 구현 완료, 부분 구현, 보류, MVP 제외 상태 구분
- `issues_created.json`에 완료 상태와 병합 근거 추가
- 이후 모든 작업에 실제 인수 조건을 가진 task 문서를 요구하는 착수 게이트 명시

## 제외 범위

- 제품 요구사항, 공개 API 필드, DB 스키마 또는 안전 정책 변경
- 미구현 웨어러블·캘린더·소셜 provider 기능 구현
- GitHub issue/PR 생성 또는 원격 상태 변경
- 기존 완료 task 문서의 소급 재작성

## 인수 조건

1. 기준 커밋과 조사일이 현황 문서에 기록된다.
2. 모든 MVP 기능 그룹 `F001`~`F011`, `F025`~`F029`가 API·DB 계약, 코드, 테스트, PR과 연결되며 없는 근거는 `—`로 표시된다.
3. 상태는 `IMPLEMENTED`, `PARTIAL`, `DEFERRED`, `MVP_EXCLUDED` 중 하나로 판정하고 의미를 문서에 정의한다.
4. 웨어러블 `F003`과 캘린더 `F011`은 구현 완료로 표시하지 않으며, 수동 폴백과 기반 구현 범위를 분리해 기록한다.
5. `F004`, `F012`~`F023`은 `MVP_EXCLUDED`로 유지한다.
6. `issues_created.json`의 각 항목에 현재 상태, 병합 PR, merge commit, 확인 근거가 기록되고 JSON 파싱이 성공한다.
7. 이후 새 작업은 구현 착수 전에 요구사항, 범위, 실제 인수 조건, 테스트, 위험이 채워진 task 문서를 가져야 한다.
8. 문서 변경만 존재하며 API·DB·런타임 동작 변경은 없어야 한다.

## 변경 예상 파일

- `backend/백엔드_기능_정리_수정본.md`
- `docs/TRACEABILITY.md`
- `issues_created.json`
- `docs/tasks/README.md`
- `docs/tasks/TASK-DOCS-001.md`

## API 영향

없음. 구현된 OpenAPI operation과 계약 문서의 차이를 기록할 뿐 공개 계약을 변경하지 않는다.

## DB·마이그레이션 영향

없음. `0001`~`0022` migration과 현재 ORM 구현을 근거로만 사용한다.

## 안전·개인정보·보안 영향

민감정보나 secret을 추가하지 않는다. 안전·개인정보 기능을 구현 완료로 판정할 때 실제 결정 규칙,
저장 경계, 테스트 근거가 모두 있는지 확인한다.

## 선행 관계와 차단 요소

- `develop`의 기준 커밋이 고정되어야 한다.
- GitHub API 상태를 추측하지 않고 병합 커밋 메시지와 저장소 diff만 증거로 사용한다.
- 외부 provider credential이 필요한 기능은 코드 골격이 있어도 보류로 판정한다.

## 테스트 계획

- `issues_created.json` JSON 파싱
- 문서에 기록한 코드·테스트·task 경로 존재 확인
- OpenAPI operation 수와 migration chain 재확인
- Markdown conflict marker, 공백 오류, 깨진 내부 경로 검사
- 문서 변경 diff 검토

## 수동 확인

1. `docs/TRACEABILITY.md`에서 MVP 기능별 상태와 근거를 확인한다.
2. 백엔드 현황 문서의 구현 API 목록을 실제 OpenAPI 목록과 비교한다.
3. `issues_created.json`의 PR과 merge commit을 `git log --first-parent`와 비교한다.

## 알려진 제한과 후속 작업

- 447개 세부 요구사항의 개별 자동 검사는 이번 범위가 아니다. 상위 그룹 상태는 가장 낮은 하위 상태를 따른다.
- GitHub issue의 실제 closed 상태는 저장소 이력으로 대체 검증했다. 원격 issue metadata 동기화는 PR 요청 시 별도로 수행한다.
- 미구현 외부 연동은 각각 별도 task 문서와 승인된 provider/credential 계획이 생긴 뒤 착수한다.

## 검증 결과

- JSON: `issues_created.json` 21건 파싱, 증거 경로 38개와 merge commit 36개 확인
- OpenAPI: 34개 operation 확인
- migration: 22개 revision, 단일 head `0022_promote_merged_data` 확인
- 문서: 내부 파일 경로 17개, Markdown 표 구조, conflict marker, trailing whitespace, `git diff --check` 통과
- backend non-integration tests: 821개 수집, 808개 통과, 13개는 Windows `tmp_path` ACL로 setup error
- integration tests: PostgreSQL test DB가 필요한 관계로 이번 문서 작업에서는 실행하지 않음
