# 백엔드 개발팀장 트랙 (BL-1 ~ BL-7)

- 기준 코드: `origin/develop` = `5a6fd26`
- 소유 모듈: `app/modules/profiles/**`, `app/modules/identity/**`, `app/modules/weekly_reports/**`,
  `app/modules/decisions/explanations.py`, `app/domain/rules/auth_provider.py`
- 공통 규칙과 병렬화 계획은 `README.md` 참조

이 트랙은 계약을 깨거나, 마이그레이션을 만들거나, 보안 경계를 건드리는 작업을 모았다.
팀원 트랙과 파일이 겹치지 않으므로 동시에 진행할 수 있다. 단 마이그레이션은 직렬이다
(`README.md` 충돌 지도 1번).

---

## BL-1. 코칭 스타일 단일화

- 선행: 없음 / 게이트: **G6 확정** — 가장 일반적인 단일 스타일로 고정하고 선택 화면 자체를 없앤다
- 짝 작업: FE-8 (온보딩 단계 제거)
- 같은 계약을 건드리는 작업: **BL-7**. 한 PR로 묶거나 순차 진행한다.
- 위험: 중간. 1단계에는 마이그레이션이 없다.

### 현재 상태

3가지 코칭 스타일(`SUPPORTIVE`, `CONCISE`, `ENERGETIC`)을 온보딩에서 받아 저장하지만,
"그래서 어디에 반영하는지"가 정해지지 않아 제거하기로 했다. 현재 사용처는 결정 설명 템플릿뿐이다.

- `backend/app/db/models/profile.py:44` CHECK 제약, `:71` `NOT NULL` 컬럼
- `backend/app/modules/decisions/explanations.py` 11곳에서 템플릿 선택에 사용
- `backend/app/modules/profiles/schemas.py:80` 온보딩 기본값 `SUPPORTIVE`

**백엔드는 이미 절반 준비돼 있다.** `coaching_style_code`에 기본값 `SUPPORTIVE`가 있어 이 필드를
보내지 않아도 온보딩이 성공한다. 따라서 이 작업의 무게는 요청 스키마가 아니라
`explanations.py`의 스타일 분기 제거에 있고, 온보딩 단계 제거는 프론트(FE-8)가 담당한다.

### 목표

모든 사용자가 동일한 컨텍스트를 받는다. 고정 스타일은 현재 기본값인 `SUPPORTIVE`다.

### 반드시 2단계로 나눌 것

AGENTS.md 10절이 "쓰기를 멈춘 릴리스에서 프로덕션 컬럼을 지우지 말 것"을 요구한다.

**1단계 (이번 릴리스)**

- 온보딩 요청과 프로필 수정 요청에서 `coaching_style_code`를 받지 않는다.
  요청 스키마에서 제거하되, 이미 배포된 클라이언트가 보내더라도 400을 내지 않고 무시한다.
- 저장 시에는 항상 단일 값(`SUPPORTIVE`)을 쓴다. 컬럼과 CHECK 제약은 그대로 둔다.
- 응답의 `coaching_style_code`는 하위 호환을 위해 유지하고 항상 `SUPPORTIVE`를 돌려준다.
- `explanations.py`는 스타일 분기를 제거하고 단일 템플릿 집합만 사용한다.
  기존에 저장된 설명 레코드는 다시 쓰지 않는다.

**2단계 (다음 릴리스, 별도 이슈)**

- 응답 필드 제거, 컬럼 드롭 마이그레이션, CHECK 제약 제거.
- 1단계 배포가 안정화되고 구버전 클라이언트가 사라진 뒤에만 착수한다.

### 인수 조건

1. 코칭 스타일 없이 온보딩을 완료할 수 있다.
2. 구버전 클라이언트가 `coaching_style_code`를 포함해 보내도 온보딩이 성공한다.
3. 온보딩으로 만들어진 모든 신규 프로필의 `coaching_style_code`가 `SUPPORTIVE`다.
4. 결정 설명이 스타일과 무관하게 같은 입력에 같은 문구를 낸다.
5. 1단계 배포 후 `coaching_style_code` 컬럼과 제약이 DB에 그대로 남아 있다.
6. 기존에 다른 스타일로 저장된 프로필을 가진 사용자의 결정 요청이 실패하지 않는다.

### 변경 예상 파일

`app/modules/profiles/schemas.py`, `app/modules/profiles/service.py`,
`app/modules/profiles/ports.py`, `app/modules/decisions/explanations.py`,
`app/db/repositories/profile.py`, `app/api/v1/profiles.py`

### API·DB 영향

- API: 요청 필드 제거(하위 호환 무시), 응답 필드 유지. `docs/API_CONTRACT.md` 해당 절 갱신.
- DB: 1단계는 마이그레이션 없음.

### 테스트

- `backend/tests/api/test_onboarding.py`: 코칭 스타일 없이 성공 / 있어도 성공
- `backend/tests/api/test_profile_settings.py`
- `backend/tests/unit/test_decision_explanations.py` (22곳이 스타일에 의존, 전면 정리 필요)
- `backend/tests/unit/test_v3_decision_explanations.py`

### 제외 범위

컬럼 드롭, 응답 필드 제거, 기존 설명 레코드 재작성.

---

## BL-2. 소셜 로그인 (Kakao → Google → Naver)

- 선행: 없음 / 게이트: **G1 해제됨** (ADR-0009 `ACCEPTED`, 2026-09-07)
- 짝 작업: FE-11
- 위험: 높음. 인증 경계.

### 착수 전 반드시 읽을 것

`docs/adr/0009-social-oauth-exchange.md`. 이 ADR은 2026-09-07에 `ACCEPTED`로 전환됐고 구현 금지가
해제됐다.

> **착수 전 확인:** 현재 그 변경이 작업 트리에만 있고 커밋되지 않았다
> (`git status`에 `M docs/adr/0009-social-oauth-exchange.md`). 구현 브랜치를 열기 전에
> 상태 변경을 먼저 커밋해 승인 기록을 남긴다.

ADR-0009가 정한 순서를 바꾸지 않는다.

1. **Kakao**: 백엔드가 authorization code를 교환하고 OIDC ID token을 검증한 뒤 Firebase custom
   token을 발급한다. 첫 직접 OAuth 구현 대상이다.
2. **Google**: 기존 Firebase provider 경로만 사용한다. 백엔드 직접 OAuth를 중복 구현하지 않는다.
3. **Naver**: Kakao 수직 슬라이스가 안정화되고 앱 공개 검수와 token revoke 운영 계약이 승인된 뒤.

### 현재 상태

- 결정적 도메인 규칙은 이미 있다: `backend/app/domain/rules/auth_provider.py`
  (`AuthProviderCode` GOOGLE·KAKAO·NAVER, state/nonce/PKCE, TTL 10분, IP 레이트리밋,
  standalone unlink 24시간, 재시도 백오프).
- API route가 없다. `backend/app/api/v1/router.py`에 auth 라우터가 등록돼 있지 않다.
- `IdentityProviderCode`는 `FIREBASE` 하나뿐이다
  (`backend/app/modules/identity/codes.py`, code-set `identity-mvp-v1`).
- ADR은 신규 code-set `identity-social-v1`을 쓰고 `identity-mvp-v1`은 건드리지 않도록 정했다.

### 목표

Kakao 로그인 수직 슬라이스를 ADR-0009 계약대로 구현한다.

### 인수 조건

1. Kakao authorization code 교환이 백엔드에서 일어나고, 프론트는 provider 시크릿을 보지 않는다.
2. OIDC ID token의 issuer(`https://kauth.kakao.com`), audience, subject를 검증한다.
   검증 실패는 `auth_provider.py`의 해당 `AuthFailureCode`로 매핑된다.
3. state·nonce·PKCE S256을 모두 강제한다. 만료된 state, 재사용된 authorization code는 거부한다.
4. 성공 시 Firebase custom token을 발급하고, 최종 세션 권한은 기존대로 Firebase ID Token이다.
5. `user_identities`에 Kakao subject를 **additive**로 추가한다. 기존 FIREBASE row를 다시 쓰지 않는다.
6. 레이트리밋(IP 분당 10회, provider redirect 시간당 60회)이 동작한다.
7. 연결 해제가 ADR의 unlink 계약대로 동작하고, 실패 시 정의된 백오프로 재시도한다.
8. provider 토큰, authorization code, 이메일이 로그에 남지 않는다.

### 변경 예상 파일

`app/api/v1/auth.py` (신규), `app/api/v1/router.py`,
`app/modules/identity/codes.py`, `app/modules/identity/service.py`, `app/modules/identity/ports.py`,
`app/integrations/oauth/kakao.py` (신규 어댑터),
`app/db/models/identity.py`, `app/db/repositories/identity.py`,
`backend/migrations/versions/00XX_social_identity.py`

### API·DB 영향

- API: 신규 엔드포인트. `docs/API_CONTRACT.md`에 절 추가.
- DB: `user_identities` 확장 마이그레이션. **마이그레이션 직렬 규칙 적용** — BL-1 2단계와 동시에
  열지 않는다.

### 보안·개인정보

- provider의 profile claim(email, 이름 등)은 폐기하고 subject만 소비한다.
- 최소 scope(`openid`)만 요청한다.
- credential은 Secrets Manager에 둔다. 소스, 픽스처, 문서, 스크린샷에 넣지 않는다.

### 테스트

security 테스트 필수: state 만료, code 재사용, nonce 불일치, PKCE 검증 실패, issuer·audience 불일치,
provider 장애, 레이트리밋 초과. 각각이 정의된 `AuthFailureCode`를 내는지 확인한다.

### 제외 범위

Naver 어댑터. Google 직접 OAuth. 계정 병합 UX.

---

## BL-3. 웨어러블 표기 제거

- 선행: 없음 / 게이트: **G2 확정**
- 짝 작업: FE-13 (프론트 표기 제거는 독립적으로 진행 가능)

### 확정된 결정 (G2)

> 웨어러블 우선 프론트에서 연동 체크 등 명시되는 부분 전부 제거. **확장성으로만 열어두고** 현재
> 서비스에는 사용자에게 표시 안 되도록.

즉 **데이터 계약은 남기고 화면 표기만 없앤다.** 이 경계는 AGENTS.md 11절의 필수 골든 시나리오
4번("웨어러블 데이터 없음 → 수동 체크인 폴백")과 충돌하지 않는다. 값 도메인을 좁혔다면 충돌했겠지만
그렇게 하지 않는다.

### 작업 순서

1. `docs/adr/0019-retire-wearable-integration.md`를 작성해 결정을 기록한다.
   `docs/adr/0016-retire-calendar-integration-and-cardio-checkin-choice.md`가 선례다.
   **"확장성으로만 열어둔다"의 경계를 명시적으로 적는다** — 무엇을 지우고 무엇을 왜 남기는지.
2. 백엔드는 동의 수집 목록에서만 제외한다.

프론트 표기 제거(FE-13)는 이 ADR을 기다릴 필요가 없다. 화면에서 없애는 것이 결정 자체이기 때문이다.

### 목표

- `WEARABLE_INTEGRATION` 동의를 신규 수집 대상에서 제외한다.
- `sleep_source_code`의 `MANUAL | WEARABLE` 값 도메인, `ConsentTypeCode.WEARABLE_INTEGRATION` 값,
  골든 시나리오 4번은 **유지**한다. 이것이 "확장성으로만 열어둠"이다.

### 인수 조건

1. 온보딩 동의 요청이 `wearable_integration` 없이 성공한다.
2. 이미 `WEARABLE_INTEGRATION` 동의 기록을 가진 사용자의 조회·삭제가 계속 동작한다.
3. `sleep_source_code = 'WEARABLE'`인 기존 체크인 행이 그대로 읽힌다.
4. 골든 시나리오 4번 테스트가 그대로 통과한다.
5. `data/` 및 계약 문서에서 웨어러블을 안전 판정 근거로 쓰지 않는다는 기존 규칙이 유지된다.

### 변경 예상 파일

`docs/adr/0019-retire-wearable-integration.md` (신규),
`app/modules/profiles/schemas.py`, `app/modules/profiles/codes.py`,
`docs/DOMAIN_RULES.md`, `docs/API_CONTRACT.md`, `AGENTS.md` (해당 절이 있으면)

### 제외 범위

`ConsentTypeCode.WEARABLE_INTEGRATION` 값 삭제, `sleep_source_code` 값 도메인 축소,
체크인 모듈 수정(팀원 트랙 소유). 기존 동의 레코드 삭제.

---

## BL-4. 주간 리포트 지표 확장

- 선행: 없음 / 게이트: 없음
- 짝 작업: FE-7 (첨부된 시안대로 화면 구성)
- 데이터 의존: 총 소모 칼로리는 BM-6이 채운다. 파일은 겹치지 않는다.

### 현재 상태

`WeeklyReportResponse`(`backend/app/modules/weekly_reports/schemas.py`)가 제공하는 값:
`counts`(완료·부분·미수행·안전중단), `completion_rate`, `persistence_rate`,
`negotiation_success_rate`, `weekday_failure_summary`, `pattern_summary`, `decision_summary`,
`adjustment_direction_code`, `next_action`, `summary`.

없는 값: **총 운동 수행 시간, 총 소모 칼로리, 평균 운동 강도, 가장 많이 한 운동, 지난주 대비 비교.**

### 목표

확정된 논의 사항대로 "수치 통계 한 눈에 + 주간 수행 결과 + 피드백 요약 + 다음 주 조정 방향"을
응답으로 제공한다.

### 추가할 값

모두 optional 필드로 추가한다(하위 호환).

| 필드 | 출처 | 비고 |
|---|---|---|
| 총 운동 수행 시간 | `workout_sessions.accumulated_progress_seconds` 합계 | 경과 시간이 아니라 진행 시간. 공식 완료 판정과 혼동하지 말 것 |
| 총 소모 칼로리 | `workout_sessions.estimated_calories_burned` 합계 | BM-6 이전에는 전부 null. **"미계산" 상태를 null로 구분**하고 0으로 뭉개지 않는다 |
| 평균 운동 강도 | 수행된 계획의 강도 코드 분포 | 기계 판독 코드로 반환. 한국어 라벨은 프론트가 만든다 |
| 가장 많이 한 운동 유형 | 수행된 세션 아이템의 training type 최빈값 | `pattern_summary.high_completion_exercise_types`와 의미가 다르므로 별도 필드 |
| 지난주 대비 완료 횟수 차이 | 직전 주 리포트의 `counts.completed` | 직전 주 리포트가 없으면 null |
| 좋았던 점 / 아쉬웠던 점 | 기존 집계에서 결정적으로 도출 | 아래 참조 |

### 좋았던 점 / 아쉬웠던 점

시안의 두 박스는 문장이지만, **결정적 규칙으로 만들고 LLM에 맡기지 않는다.** 코드 리스트로
반환하고 프론트가 문구로 옮기는 방식을 권장한다. `weekly_reports/narration.py`는 문체만 바꿀 수
있고 수치·코드·판정은 바꿀 수 없다는 기존 경계(`NARRATION.md`)를 유지한다.

미수행·부분 수행 사유는 이미 `not_completed_reason_counts`로 집계된다. 이를 근거로 삼는다.

### 톤 규칙 (AGENTS.md 7절)

- 미수행은 학습 신호이지 벌점이 아니다. 아쉬웠던 점 문구가 사용자를 탓하지 않아야 한다.
- 진단·치료·처방 표현을 쓰지 않는다.
- 통증·이상반응으로 중단한 세션에 대해서는 가벼운 문체를 쓰지 않는다.

### 인수 조건

1. 새 필드가 모두 optional이고, 구버전 클라이언트가 기존 필드만으로 계속 동작한다.
2. 칼로리가 아직 계산되지 않은 주간은 총 소모 칼로리가 `null`이며 `0`이 아니다.
3. 직전 주 리포트가 없으면 지난주 대비 값이 `null`이다.
4. 같은 주간 데이터에 대해 리포트를 두 번 생성해도 동일한 값이 나온다.
5. 안전 중단 세션이 포함된 주간의 문구가 가벼운 문체를 쓰지 않는다.
6. LLM narration이 꺼져 있거나 실패해도 모든 수치 필드가 채워진다.

### 변경 예상 파일

`app/modules/weekly_reports/schemas.py`, `app/modules/weekly_reports/service.py`,
`app/modules/weekly_reports/ports.py`, `app/db/repositories/weekly_report.py`,
`docs/API_CONTRACT.md`

### 테스트

`backend/tests/unit/`의 주간 리포트 테스트, `backend/tests/integration/test_weekly_report_repository.py`,
LLM 실패 시 결정적 폴백 테스트.

### 제외 범위

프론트 화면 구성(FE-7). 칼로리 계산 자체(BM-6). 주간 계획 조정 로직 변경.

---

## BL-5. 프로필 이미지 변경 미반영 원인 규명과 수정

- 선행: 없음 / 게이트: 없음
- 짝 작업: FE-5

### 현재 상태

업로드 경로는 백엔드·프론트 모두 구현돼 있다.

- `backend/app/modules/profiles/images.py` (10MB 상한, JPEG·PNG·WebP 매직바이트 검증)
- `backend/app/integrations/s3/profile_image.py`
- `frontend/src/features/home/MyPageProfileEditor.tsx:375`

### 가장 유력한 가설 (미확인)

`S3ProfileImageAdapter.put()`이 `BotoCoreError`, `ClientError`, `OSError`를 잡아 **경고 로그만 남기고
`False`를 반환**한다. 버킷은 `exercise_media_s3_bucket`을 재사용하고 prefix는 `profile-images/`다
(`build_s3_profile_image_adapter`). EC2 인스턴스 역할에 해당 prefix의 `s3:PutObject`가 없으면
AccessDenied → `False` → 사용자에게는 아무 일도 일어나지 않은 것처럼 보인다.

저장소의 참조 정책 `infra/aws/ec2-staging-exercise-media-policy.json`에는
`ManagePrivateProfileImages` 문(`s3:GetObject`, `PutObject`, `DeleteObject` on `profile-images/*`)이
**있다.** 그러나 이 파일은 참조 문서일 뿐 실제 역할과 일치하지 않는 것으로 확인된 적이 있으므로,
살아 있는 역할을 직접 확인해야 한다.

### 진단 절차 (코드 수정 전에 수행)

1. 실제 역할의 인라인 정책을 확인한다.
   `aws iam list-role-policies --role-name helkki-staging-ec2-role`,
   이어서 각 정책의 `get-role-policy`.
   `profile-images/*`에 대한 `s3:PutObject` 허용이 실제로 있는지 본다.
2. 컨테이너 로그에서 `profile_image_s3_put_failed` 또는 `profile_image_s3_presign_failed`
   경고가 찍히는지 확인한다.
3. 위 둘로 원인이 확정되지 않으면 프론트 요청이 실제로 나가는지, 응답 코드가 무엇인지 확인한다.

원인이 권한이면 코드 변경 없이 정책만 맞추면 된다. 그래도 아래 관측성 개선은 별도로 수행한다.

### 목표

원인을 확정해 고치고, 같은 실패가 다시 조용히 넘어가지 않게 한다.

### 인수 조건

1. 프로필 사진을 바꾸면 마이페이지와 홈 화면에 즉시 반영된다.
2. 저장에 실패했을 때 사용자에게 실패가 보인다. 성공한 것처럼 보이는 경로가 없다.
3. 저장소 어댑터 실패가 공통 에러 스키마의 명확한 코드로 매핑된다.
4. 실패 로그에 사용자 식별자, 이미지 내용, presigned URL이 남지 않는다.
5. 원인이 IAM이었다면 `infra/aws/ec2-staging-exercise-media-policy.json`이 실제 역할과 일치한다.

### 변경 예상 파일

`app/modules/profiles/images.py`, `app/api/v1/profiles.py`,
`app/integrations/s3/profile_image.py`, `infra/aws/ec2-staging-exercise-media-policy.json`

### 제외 범위

이미지 리사이즈·크롭. CDN 도입. 프론트 화면 정리(FE-5).

---

## BL-6. 약관·개인정보 처리방침 콘텐츠 계약

- 선행: 없음 / 게이트: 없음
- 짝 작업: FE-14 이후의 마이페이지 작업

### 현재 상태

- 마이페이지 "이용약관" 행이 빈 스텁이다(`frontend/src/features/home/homeSecondaryModel.ts:351`).
- 로그인 화면은 "계속하면 서비스 이용약관과 개인정보 처리방침에 동의하게 됩니다"라고 표시하지만
  (`frontend/src/features/auth/LoginScreen.tsx:350`) 실제로 볼 수 있는 문서가 없다.
- 동의 유형 코드는 있다: `GENERAL_PERSONAL_DATA`, `SENSITIVE_DATA`, `WEARABLE_INTEGRATION`,
  `CALENDAR_INTEGRATION`, `MARKETING` (`app/modules/profiles/codes.py:22`).
- `consent_policy_version` 설정값이 이미 있다(`app/core/config.py`).

### 목표

약관 본문을 버전과 함께 제공하고, 사용자가 동의한 버전을 추적할 수 있게 한다.

### 설계 방향

본문 자체는 법무·PM이 쓴다. 백엔드는 **본문을 코드에 하드코딩하지 않고** 버전이 붙은 콘텐츠를
제공하는 계약을 만든다. 최소 형태는 정적 문서와 버전 메타데이터를 반환하는 읽기 엔드포인트다.

`CALENDAR_INTEGRATION`은 ADR-0016으로 폐기됐고 `WEARABLE_INTEGRATION`은 BL-3에서 폐기 예정이므로,
신규 수집 대상 동의 목록에서 제외한다. 값 자체는 기존 기록 때문에 남긴다.

### 인수 조건

1. 약관·개인정보 처리방침 본문과 버전을 조회할 수 있다.
2. 사용자가 동의한 시점의 정책 버전이 기록에 남는다.
3. 폐기된 동의 유형이 신규 수집 목록에 나타나지 않는다.
4. 본문이 소스 코드에 하드코딩돼 있지 않다.

### 변경 예상 파일

`app/api/v1/profiles.py` 또는 신규 라우터, `app/modules/profiles/schemas.py`,
`app/modules/profiles/codes.py`, `docs/API_CONTRACT.md`

### 제외 범위

약관 본문 작성(PM·법무). 동의 철회 플로우 재설계.

### 선행 확인

본문 초안이 준비돼 있는지 PM에게 먼저 확인한다. 없으면 계약과 빈 콘텐츠 구조까지만 만들고
본문 반영은 후속 이슈로 남긴다.

---

## BL-7. ADR-0017 잔여 정리: 장소·성별·키 legacy 필드

- 선행: 없음 / 게이트: **G7 확정**
- 짝 작업: FE-5 (마이페이지), BM-4 (체크인 장소)
- 같은 계약을 건드리는 작업: **BL-1**. 한 PR로 묶거나 순차 진행한다.

### 이것은 새 결정이 아니라 미완 실행이다

G7("온보딩에서 집·헬스장 선택 자체를 제거, 운동 장소는 체크인에서 선택")은
`docs/adr/0017-onboarding-input-reduction-and-ungated-base-routine.md`(**ACCEPTED**, 2026-09-02)가
이미 같은 내용으로 결정한 사항이다.

> 성별, 키, BMI, 온보딩 장소, 온보딩 1회 운동시간, 보유 장비는 온보딩에서 수집하지 않는다.
> 운동 장소와 1회 운동시간은 Daily Check-in의 `location_code`와 `available_time_minutes`로만 받는다.
> 프로필에 기본값을 두지 않는다.

**새 ADR을 쓰지 않는다.** ADR-0017을 끝까지 시행하는 작업이다.

### 이미 끝난 부분 (다시 하지 말 것)

- `OnboardingUpsertRequest`에서 장소·시간·성별·키가 이미 optional 또는 기본값이다. 온보딩은
  이 값들 없이 성공한다.
- 프론트 온보딩 화면에 장소·성별·키 입력이 없다.
- 기본 루틴 생성이 장소를 후보 게이트로 쓰지 않는다. 서버 기본 시간 상수 30분이 적용돼 있다.

### 남은 부분

ADR-0017이 "제거 대상 요청 필드는 즉시 삭제하지 않고 legacy로 표시해 write 호환 기간을 둔 뒤
별도 릴리스에서 요청 필드와 컬럼을 순서대로 제거한다"고 정했다. 그 별도 릴리스가 이 작업이다.

**1단계 (이번 릴리스)**

- `MeProfile` 응답과 `PATCH /api/v1/me/profile`에서 `preferred_location_code`,
  `available_location_codes`, `height_cm`, `sex_code`를 **더 이상 수정 대상으로 받지 않는다.**
  응답 필드는 하위 호환을 위해 유지한다.
- 구버전 클라이언트가 이 필드들을 보내도 400을 내지 않고 무시한다.
- `input_snapshot.profile` allowlist에서 장소·시간·주의 부위가 빠졌는지 확인한다.
  ADR-0017이 요구했으나 시행 여부를 별도로 검증해야 한다. **기존 snapshot은 rewrite하지 않는다** —
  과거 결정의 재현 근거가 저장된 snapshot뿐이기 때문이다.

**2단계 (다음 릴리스, 별도 이슈)**

- 응답 필드 제거와 컬럼 드롭 마이그레이션. BL-1 2단계와 순서를 정해 하나씩 진행한다.

### 체중은 제거 대상이 아니다

`weight_kg`는 온보딩 **필수** 입력이며(`Field(ge=25, le=300)`) 유지한다. BM-6의 칼로리 계산이
체중을 쓴다. ADR-0017의 제거 목록에도 체중은 없다.

### 인수 조건

1. 마이페이지에서 장소·성별·키를 수정하는 요청이 더 이상 프로필을 바꾸지 않는다.
2. 구버전 클라이언트가 그 필드를 포함해 보내도 요청이 성공한다.
3. `MeProfile` 응답에 해당 필드가 그대로 남아 있다(하위 호환).
4. 온보딩이 장소·성별·키 없이 완료되고 기본 루틴이 생성된다.
5. 체크인의 `location_code`가 프로필 값과 무관하게 동작한다 (BM-4와 함께 확인).
6. 기존 `input_snapshot`을 읽는 경로가 깨지지 않는다.
7. 1단계 배포 후 해당 컬럼들이 DB에 그대로 남아 있다.

### 변경 예상 파일

`app/modules/profiles/schemas.py`, `app/modules/profiles/service.py`,
`app/db/repositories/profile.py`, `app/api/v1/profiles.py`,
`docs/API_CONTRACT.md`, `docs/adr/0017-onboarding-input-reduction-and-ungated-base-routine.md`
(시행 완료 기록 추가)

### 테스트

- `backend/tests/api/test_onboarding.py`, `test_profile_settings.py`
- 구버전 요청 호환 테스트
- 기존 snapshot read 경로 회귀 테스트

### 제외 범위

컬럼 드롭. 응답 필드 제거. 체중 제거. 체크인 측 변경(BM-4). 마이페이지 화면(FE-5).
