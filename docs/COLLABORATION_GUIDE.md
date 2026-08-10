# COLLABORATION_GUIDE.md

## 1. 기본 원칙

- 한 이슈에는 primary owner 한 명만 둔다.
- 한 브랜치에는 한 이슈만 담는다.
- 계약 변경과 기능 구현을 가능한 한 분리한다.
- 다른 담당자의 미커밋 작업을 덮어쓰지 않는다.
- `main`, `develop`에 직접 커밋하지 않고 force push를 금지한다.
- 건강·안전·개인정보·공개 계약 변경은 지정 공동 검토 없이 병합하지 않는다.

## 2. 브랜치 전략

기본은 짧게 유지하는 trunk-based 방식이다.

| 브랜치 | 용도 |
|---|---|
| `main` | 배포 가능한 보호 브랜치 |
| `develop` | 통합 브랜치. 모든 작업 브랜치 PR의 기본 병합 대상 |
| `feat/<issue>-<slug>` | 기능 |
| `fix/<issue>-<slug>` | 버그 |
| `docs/<issue>-<slug>` | 문서·계약 |
| `chore/<issue>-<slug>` | 도구·환경 |

`develop` 사용을 확정했다. 작업 브랜치는 `develop`에서 분기하고 `develop`으로 PR한다. `main`은 배포 가능 상태만 유지하며 `develop` → `main` 릴리스 PR로만 갱신한다.

## 3. 커밋 규칙

Conventional Commits의 최소 집합을 사용한다.

```text
feat(scope): 사용자에게 보이는 기능
fix(scope): 결함 수정
docs(scope): 문서·계약
test(scope): 테스트
refactor(scope): 동작 없는 구조 개선
chore(scope): 도구·환경
```

제목은 무엇이 바뀌었는지 명령형으로 쓰고, API/DB/안전 변경은 본문에 영향과 호환성 전략을 적는다. 임시 커밋은 PR 병합 전에 정리한다.

## 4. 이슈 준비 완료 조건

- 배경과 사용자 가치
- 포함·제외 범위
- 인수 조건
- primary owner
- 변경 예상 경로
- API, DB, 안전, 개인정보 영향
- 선행 이슈와 차단 요소
- 요구사항 ID와 테스트 케이스 ID

세부 양식은 `docs/tasks/TEMPLATE.md`와 GitHub issue template을 사용한다.

## 5. PR 규칙

PR은 가능하면 리뷰 가능한 작은 단위로 유지하며 다음을 포함한다.

- 해결한 문제와 범위
- 변경 파일군
- API/DB/보안·개인정보 영향
- 실행한 테스트와 실제 결과
- 수동 확인 절차
- 알려진 제한과 후속 작업
- 관련 요구사항·인수 조건·테스트 ID

PR 작성자가 자기 diff를 먼저 검토한다. 생성 파일, 비밀값, 로그의 민감정보, unrelated refactor가 없는지 확인한다.

## 6. 리뷰·승인 매트릭스

| 변경 | 최소 승인 |
|---|---|
| 프론트 내부 | 프론트 또는 개발팀장 1명 |
| 일반 API/DB | 백엔드 + 영향받는 프론트 |
| agent/조정 | 개발팀장 |
| 안전·통증·복귀 | 개발팀장 + PM + 필요한 외부 검수 증적 |
| MVP 범위 | PM + 개발팀장 |
| 인증·삭제·민감정보 | 백엔드 + 개발팀장 |

작성자는 승인자 수에 포함하지 않는다. 긴급 수정도 사후가 아닌 병합 전 리뷰를 원칙으로 한다.

## 7. 병합 정책

- PR 기본 타깃은 `develop`이며 `main` PR은 릴리스 승격에만 사용
- 필수 CI 성공
- unresolved conversation 0개
- 필요한 계약 문서 동시 갱신
- 마이그레이션이 있으면 forward와 rollback/forward-fix 확인
- squash merge를 기본으로 하되 팀이 전체 커밋 보존을 합의하면 변경 가능
- 병합 후 브랜치 삭제

## 8. 충돌과 변경 관리

- 문서 충돌은 `docs/README.md` 우선순위를 따른다.
- 기존 결정 변경은 ADR과 영향받는 계약을 같은 PR에서 수정한다.
- 공개 필드 삭제·이름 변경은 즉시 하지 않는다. 추가 → 양쪽 지원 → 사용 중단 → 후속 제거 순서를 따른다.
- 안전 규칙 변경은 policy/ruleset version과 골든 테스트를 함께 갱신한다.

## 9. 비밀값과 개인정보

- `.env`, provider secret, Firebase service credential을 커밋하지 않는다.
- 토큰, 이메일, 전체 이름, 체크인 원문, 원시 건강·웨어러블 데이터를 로그·fixture·스크린샷에 넣지 않는다.
- 테스트 사용자는 합성 데이터만 사용한다.
- 외부 LLM에 직접 식별자와 원시 건강 데이터를 보내지 않는다.

## 10. 대안과 선택 이유

Git Flow 전체를 기본으로 선택하지 않았다. 장기 release/hotfix 브랜치는 4명 팀의 병합 비용을 높인다. 무리뷰 직접 커밋은 빠르지만 계약과 안전 불변식의 회귀를 추적할 수 없어 허용하지 않는다.

## 11. 아직 확정되지 않은 사항

- `main`·`develop` branch protection 실제 적용 (저장소 admin 권한 보유자 필요, §12 참고)
- required review 수
- 실제 GitHub handle 기반 `CODEOWNERS`
- CI에서 필수로 고정할 formatter/type checker 명령

## 12. 팀 확인 질문

- `main`·`develop` 직접 push 차단: 팀 계정에는 저장소 admin 권한이 없어 branch protection을 설정할 수 없음이 확인되었다. `SKNETWORKS-FAMILY-AICAMP` org owner 또는 저장소 admin에게 설정을 요청해야 한다. 그전까지 직접 push 금지는 규칙으로만 강제된다.
- squash merge를 팀 표준으로 채택할 것인가?
- 주 1회 계약 변경 검토 시간을 고정할 것인가?
