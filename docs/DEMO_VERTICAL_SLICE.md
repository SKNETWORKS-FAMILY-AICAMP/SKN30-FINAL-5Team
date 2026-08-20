# 수직 슬라이스 데모 실행 안내

React Native 앱이 실제 FastAPI와 PostgreSQL 16을 사용해 온보딩부터 운동 완료까지 수행하는 데모를
재현하는 절차다. 정적 preview가 아니라 실제 API 호출이며, 인증은 Firebase 테스트 프로젝트의 실제
ID token을 사용한다.

## 0. 데모의 경계

- **합성 데이터만 사용한다.** 운동 카탈로그는 이 데모를 위해 만든 합성 콘텐츠이고 도메인 검수를
  받지 않았다. 실제 사용자에게 제공하는 운동 처방이 아니다.
- **전용 DB만 사용한다.** seed 스크립트는 이름이 `*_test` 또는 `*_demo`가 아닌 데이터베이스와
  `local`/`test`가 아닌 `APP_ENV`를 거부한다.
- **외부 캘린더(Google) 연동은 없고 보류됐다.** ADR-0010 "구현 보류" 참고. 앱의 캘린더 화면은
  외부 연동이 아니라 지난 운동 기록을 보여주는 앱 내 월간 캘린더다.
- **웨어러블 연동은 없다.** 수동 체크인이 정상 경로다.
- 비밀값은 저장소에 넣지 않는다. `frontend/.env.local`과 셸 환경변수만 사용한다.

## 0.1 데이터베이스 두 개를 분리한다

컨테이너 하나에 데이터베이스 두 개를 둔다.

| 데이터베이스 | 용도 |
|---|---|
| `exercise_app_demo` | 실행 중인 데모. 합성 카탈로그와 데모 계정이 만든 데이터 |
| `exercise_app_test` | pytest 전용 스크래치. 테스트 실행마다 다시 만든다 |

하나로 합치면 repository 통합 테스트가 실패한다. 그 테스트들은 카탈로그 lookup 행을 직접 넣으면서
해당 테이블이 비어 있다고 가정하는데, 데모 seed가 같은 행을 이미 넣어 두기 때문이다.

## 0.2 빠른 실행

아래 2~11절을 감싼 헬퍼 스크립트가 있다.

```powershell
.\scripts\demo-local.ps1 up      # PostgreSQL + migration + 합성 seed
.\scripts\demo-local.ps1 api     # 미적용 migration 반영 후 FastAPI 실행 (0.0.0.0:8000)
.\scripts\demo-local.ps1 share   # 현재 LAN IP를 앱 설정에 반영하고 공유 주소 출력 (9.1절)
.\scripts\demo-local.ps1 seed    # 합성 카탈로그만 다시 설치
.\scripts\demo-local.ps1 rules   # 안전규칙 번들 적재 + 규칙 보유 카탈로그 활성화 (4.1절)
.\scripts\demo-local.ps1 reset   # 데모 사용자 삭제 후 재seed
.\scripts\demo-local.ps1 test    # 백엔드·프론트엔드 검증 전체
.\scripts\demo-local.ps1 psql    # 데모 DB psql 접속
.\scripts\demo-local.ps1 down    # 컨테이너 제거
```

Firebase 값은 스크립트가 만들지 않는다. `FIREBASE_PROJECT_ID`와
`GOOGLE_APPLICATION_CREDENTIALS`는 6절대로 직접 설정하고, 앱 설정은 7절대로 채운다.

`api` 명령은 승인된 온보딩 데모값을 주입한 직후
`CONSENT_POLICY_VERSION`, `ONBOARDING_PRIMARY_GOAL_CODES`,
`ONBOARDING_EXPERIENCE_LEVEL_CODES`를 검사한다. null·빈 문자열·공백 또는 빈 코드 목록이면
누락된 키 이름만 출력하고 non-zero로 종료하며 FastAPI를 시작하지 않는다. 이 사전검사는 서버의
`503 PROFILE_CONFIGURATION_UNAVAILABLE` fail-closed 동작을 대체하거나 완화하지 않는다.

아래는 스크립트가 실행하는 개별 단계다.

## 1. PostgreSQL 16 시작

```powershell
docker run -d --name helkki-demo-pg `
  -e POSTGRES_USER=exercise_app `
  -e POSTGRES_PASSWORD=local_dev_only `
  -e POSTGRES_DB=exercise_app_demo `
  -p 55432:5432 postgres:16
```

준비 확인:

```powershell
docker exec helkki-demo-pg pg_isready -U exercise_app -d exercise_app_demo
```

## 2. 백엔드 환경변수

`onboarding_*`와 `CORS_ALLOWED_ORIGINS`는 JSON 배열과 쉼표 구분 문자열을 모두 받는다.
아래 예시는 JSON 배열 형태를 쓴다.

```powershell
$env:APP_ENV = "local"
$env:DATABASE_URL = "postgresql+psycopg://exercise_app:local_dev_only@localhost:55432/exercise_app_demo"
$env:CONSENT_POLICY_VERSION = "demo-consent-v1"
$env:ONBOARDING_PRIMARY_GOAL_CODES = '["GENERAL_FITNESS"]'
$env:ONBOARDING_EXPERIENCE_LEVEL_CODES = '["BEGINNER"]'
# local/test 전용 생년월일 암호화 키(32바이트 base64). 운영은 별도 KMS adapter를 사용한다.
$env:BIRTHDATE_ENCRYPTION_KEY_BASE64 = [Convert]::ToBase64String((1..32 | ForEach-Object { 0 }))
# Firebase ID token 검증에 사용할 테스트 프로젝트 ID
$env:FIREBASE_PROJECT_ID = "<firebase-test-project-id>"
```

`FIREBASE_PROJECT_ID`가 없으면 인증이 fail-closed 상태가 되어 모든 인증 요청이
`503 AUTH_PROVIDER_UNAVAILABLE`을 반환한다. 이는 의도된 동작이며 로컬 우회 경로는 제공하지 않는다.

Firebase Admin이 ID token 서명을 검증하려면 서비스 계정 자격 증명이 필요하다. 저장소 밖 경로를
가리키게 한다. 앱이 `backend/.env`에서 직접 읽으므로 셸에서 내보낼 필요는 없다.

```
GOOGLE_APPLICATION_CREDENTIALS=C:/path/outside/repo/firebase-service-account.json
```

Windows 경로는 슬래시로 적는다. `.env`의 백슬래시는 이스케이프로 해석되어 경로가 조용히
깨진다. 값을 비워 두면 Application Default Credentials로 대체된다.

## 3. 마이그레이션 적용

```powershell
uv sync --frozen --group dev
uv run alembic -c backend/alembic.ini upgrade head
```

## 4. 합성 데모 seed

```powershell
uv run python -m backend.scripts.demo_seed seed
```

`seed`는 멱등하다. 이미 있는 데모 카탈로그는 지우지 않고 재사용한다. 저장된 routine과 decision이
`ON DELETE RESTRICT`로 카탈로그를 참조하기 때문이다.

사용자 데이터까지 지우고 처음부터 다시 하려면:

```powershell
uv run python -m backend.scripts.demo_seed reset
```

`reset`은 `users` 행을 모두 삭제하고 연결된 프로필·체크인·결정·세션을 cascade로 정리한 뒤 카탈로그를
다시 설치한다. 앱에서 같은 Firebase 계정으로 다시 로그인하면 온보딩부터 시작한다.

seed가 설치하는 내용:

- 합성 카탈로그 1개(`demo-synthetic-v1`, `manifest_metadata.synthetic = true`)
- 준비 3 / 본운동 17 / 마무리 3, 총 23개 운동과 목표 연결·처방
- 10~60분 요청 시간에 대해 `estimated_duration_seconds`를 정확히 맞출 수 있는 구성

## 4.1 안전규칙 적재와 카탈로그 활성화

합성 카탈로그에는 **안전규칙이 하나도 없다.** 규칙이 없으면 `evaluate_safety`가
`rule_set = None`을 받고 설계대로 fail-closed하여 `FAILED`를 반환한다. 결과적으로 체크인에서
불편을 입력하거나 온보딩에서 주의 부위를 등록한 사용자는 루틴을 받지 못한다. 심각도와 무관하며
`MILD`도 동일하다.

승인된 규칙 354건과 대체운동 238건은 별도 번들에 있고, 규칙은 그 번들의 카탈로그에
`catalog_version_id`로 붙어 있다. 따라서 적재만으로는 반영되지 않고 해당 카탈로그를 활성화해야
한다.

```powershell
.\scripts\demo-local.ps1 rules
```

### 현재 이 명령은 활성화 단계에서 실패한다

적재된 카탈로그에는 `exercise_prescription_profiles`와 `exercise_goal_tag_links`가 **0건**이다.
`RoutineRepository.get_creation_context`가 이 두 테이블을 inner join하므로, 활성화해도 루틴 후보가
하나도 나오지 않아 **루틴 생성 자체가 불가능해진다.** `CatalogImporter`는 이 두 테이블을 만들지
않는다 — 합성 카탈로그가 존재하는 이유가 이것이다.

`catalog_activate`는 이 상태를 감지하면 검수 여부와 무관하게 거부한다. 서명이 없는 게 아니라
내용이 없는 문제이므로 `--demo-unreviewed`로도 통과하지 않는다.

```
refusing to activate 'kspo-mvp-v0.2.0': no routine could be built from it -
exercise_prescription_profiles=0, exercise_goal_tag_links=0.
```

즉 안전규칙을 데모에 반영하려면 **적재된 카탈로그에 처방·목표 연결 데이터를 먼저 만들어야 한다.**
승인 절차로 해결되는 문제가 아니다.

이 명령은 두 단계를 수행한다.

```powershell
uv run python -m backend.scripts.catalog_data_load load
uv run python -m backend.scripts.catalog_activate activate kspo-mvp-v0.2.0 --demo-unreviewed
```

`kspo-mvp-v0.2.0`을 쓰는 이유는 번들에서 CARDIO·MOBILITY·STRENGTH를 모두 가진 유일한 카탈로그이기
때문이다. 나머지는 STRENGTH만 있어 준비·마무리 구간을 채울 수 없다.

### `--demo-unreviewed`가 필요한 이유

`ck_catalog_versions_production_approval`은 활성화된 카탈로그에
`review_method_code = 'DOMAIN_REVIEWER'`와 `status_interpretation_code = 'PRODUCTION_APPROVED'`를
요구한다. 번들 카탈로그는 `AGENT_ONLY` / `PIPELINE_COMPATIBILITY_ONLY`로 들어온다 —
**운동 카탈로그 자체는 도메인 검수를 받은 적이 없다.** ISSUE-53은 규칙과 대체운동만 승인했다.

`catalog_activate`는 이 조건을 만족하지 않는 카탈로그를 기본적으로 거부한다.
`--demo-unreviewed`는 검수 완료 전 데모에서만 쓰는 우회로이며,
`APP_ENV=local|test`와 `*_demo`/`*_test` 데이터베이스에서만 동작하고,
누락된 검수를 `manifest_metadata.demo_activation`에 기록한다.
**이 플래그로 만든 데이터베이스는 staging이나 production으로 승격하지 않는다.**

### 활성화 이후 주의사항

- ACTIVE 카탈로그는 하나뿐이므로 `demo-synthetic-v1`은 DEPRECATED가 된다. 그 카탈로그로 만든
  기존 루틴은 결정 생성이 멈춘다. `reset` 후 다시 온보딩하면 새 카탈로그로 루틴이 생성된다.
- `seed`와 `reset`은 합성 카탈로그를 다시 ACTIVE로 만든다. **둘 중 하나를 실행했다면 `rules`를
  다시 실행해야 한다.**

## 5. FastAPI 실행

에뮬레이터나 실기기에서 접속하려면 `0.0.0.0`으로 바인딩해야 한다.

```powershell
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

확인:

```powershell
curl http://localhost:8000/api/v1/health/ready   # {"status_code":"READY"}
```

## 6. Firebase 테스트 프로젝트

1. Firebase 콘솔에서 **테스트 전용** 프로젝트를 만든다.
2. Authentication → Sign-in method → **이메일/비밀번호**를 사용 설정한다.
3. 프로젝트 설정 → 내 앱 → 웹 앱을 추가하고 SDK 설정값을 확인한다.
4. 서비스 계정 키를 발급해 저장소 밖에 두고 `GOOGLE_APPLICATION_CREDENTIALS`로 가리킨다.

실제 사용자 계정을 쓰지 않는다. 데모 계정 이메일과 비밀번호는 문서·스크린샷·로그에 남기지 않는다.

## 7. 프론트엔드 환경변수

```powershell
Copy-Item frontend/.env.example frontend/.env.local
```

`frontend/.env.local`을 채운다. `.env.*`는 gitignore 대상이다.

API 주소는 **앱이 실행되는 기기 기준**이다.

| 실행 환경 | `EXPO_PUBLIC_API_BASE_URL` | CORS 필요 |
|---|---|---|
| 웹(`npm run web`) | `http://127.0.0.1:8000` | 예 |
| Android 에뮬레이터 | `http://10.0.2.2:8000` | 아니오 |
| iOS 시뮬레이터 | `http://127.0.0.1:8000` | 아니오 |
| 실제 기기 | `http://<개발 PC의 LAN IP>:8000` | 아니오 |

브라우저에서는 `localhost`가 아니라 `127.0.0.1`을 쓴다. `uvicorn --host 0.0.0.0`은 IPv4만
바인딩하는데 브라우저는 `localhost`를 `::1`(IPv6)로 먼저 해석해 연결이 거부되고, 앱에는 일반적인
네트워크 오류로만 보인다. 확인 방법:

```powershell
curl http://127.0.0.1:8000/api/v1/health/live   # 200
curl http://[::1]:8000/api/v1/health/live       # 실패하면 IPv6 미수신
```

Android 에뮬레이터의 `10.0.2.2`는 호스트 루프백을 가리키는 예약 주소다. 실제 기기는 PC와 같은
네트워크에 있어야 하고 방화벽에서 8000 포트를 열어야 한다.

값을 바꾸면 Expo 개발 서버를 다시 시작한다. `EXPO_PUBLIC_*`는 번들 시점에 삽입된다.

## 8. 앱 실행

가장 간단한 방법은 브라우저다. Android Studio나 Xcode가 필요 없다.

```powershell
cd frontend
npm ci
npm run web       # http://localhost:8081
```

브라우저는 cross-origin 요청을 하므로 백엔드에 `CORS_ALLOWED_ORIGINS`가 설정돼 있어야 한다.
`demo-local.ps1 api`는 이 값을 자동으로 설정한다. 직접 실행할 때는 2절에 다음을 추가한다.

```powershell
$env:CORS_ALLOWED_ORIGINS = "http://localhost:8081,http://127.0.0.1:8081"
```

웹으로 실행할 때 `EXPO_PUBLIC_API_BASE_URL`은 `http://localhost:8000`이어야 한다.

네이티브 빌드로 확인하려면:

```powershell
npm run android   # 또는 npm run ios
```

네이티브 클라이언트는 Origin 헤더를 보내지 않으므로 `CORS_ALLOWED_ORIGINS`가 필요 없다.

설정이 비어 있으면 앱은 로그인 화면 대신 "설정이 필요해요" 화면에서 누락된 키 이름을 보여준다.
값 자체는 표시하지 않는다.

## 9. 데모 사용자 여정

1. **Splash** → 부팅
2. **로그인/회원가입** → Firebase 이메일/비밀번호. 첫 실행은 회원가입으로 계정을 만든다.
3. **사용자 생성·조회** → 첫 인증 요청이 내부 사용자를 만들고 `GET /api/v1/me`로 상태를 읽는다.
4. **온보딩** → 닉네임, 생년월일, 장소, 장비, 희망 시간, 주간 횟수, 주의 부위, 필수 동의
   (`PUT /api/v1/me/onboarding`)
5. **기본 루틴 생성** → 홈에서 "기본 루틴 만들기" (`POST /api/v1/routines`)
6. **오늘 체크인** → 피로도, 가능 시간, 불편 부위, 이상 반응 (`PUT /api/v1/daily-contexts/{date}`)
7. **결정 실행** → `POST /api/v1/decisions`
8. **최종 추천 표시** → 최종 루틴 하나와 선택적 REST opt-out
9. **명시적 선택** → `POST /api/v1/decisions/{id}/selection`
10. **세션 시작** → `PATCH /workout-sessions/{id}/start`, 0초부터 경과 타이머 시작
11. **블록별 완료 체크** → `PATCH /workout-sessions/{id}/items/{plan_item_id}`
12. **세션 종료** → `PATCH /workout-sessions/{id}/finish` (COMPLETED 또는 PARTIAL)
13. **결과와 피드백** → 서버가 계산한 상태 표시, `POST /workout-sessions/{id}/feedback`
14. **홈 복귀** → 오늘 상태 반영

### 함께 확인할 수 있는 경로

| 확인 항목 | 조작 |
|---|---|
| 안전 veto와 REST | 체크인에서 무릎 불편 "심함" 선택 → 계획 없이 REST 안내 |
| 중대한 이상 반응 | 체크인에서 "가슴 압박감 또는 통증" 선택 → 선택지 없는 중단 화면 |
| REST 선택 후 압박 없음 | 결정 화면에서 "오늘은 쉬기" → 홈에 휴식 안내만 표시 |
| 운동 중 안전 중단 | 세션에서 "통증·이상 반응 알리기" → 부위 선택 → 즉시 중단 |
| 블록 완료 전 종료 불가 | 세션 시작 직후 "운동 마치기"가 비활성 |
| 미수행 기록 | 세션에서 "오늘은 못 했어요" → 이유 선택 |
| 운동 자세·설명 | 세션 블록의 "자세 보기" (`GET /api/v1/exercises/{id}`) |
| stale 체크인 | 체크인을 두 번 저장한 뒤 이전 화면에서 재시도 → 최신 상태로 재시도 안내 |
| 주간 리포트 게이트 | 홈 → 주간 리포트. 열린 주에는 생성 거부 안내 |
| 프로필과 계정 삭제 | 홈 → 내 프로필 |
| 운동 기록 캘린더 | 홈 → 캘린더. 월간 완료/부분/휴식/미수행과 주간 리포트 진입 |

## 9.1 같은 네트워크의 팀원과 함께 보기

배포된 데모 주소는 없다. 이 데모는 개발 서버이므로 실행 중인 PC가 켜져 있는 동안, 같은 네트워크에
있는 팀원만 접속할 수 있다.

팀원이 열 주소: `http://<개발 PC의 LAN IP>:8081`

가장 쉬운 방법은 `share` 명령이다. 현재 LAN IP를 찾아 `frontend/.env.local`에 반영하고, 방화벽
규칙 유무를 확인한 뒤 공유할 주소를 알려준다.

```powershell
.\scripts\demo-local.ps1 share
```

**LAN IP는 네트워크가 바뀔 때마다 달라진다.** 한 세션에서 172.30.1.91 → 192.168.219.192 →
192.168.0.62로 세 번 바뀐 적이 있다. 낡은 값이 남아 있으면 앱에는 단순한 "서버에 연결하지
못했습니다"로만 보이므로, 공유 전에는 매번 `share`를 실행한다.

수동으로 맞출 경우 세 가지가 필요하다.

1. **API 주소를 LAN IP로.** `frontend/.env.local`의 `EXPO_PUBLIC_API_BASE_URL`을
   `http://<LAN IP>:8000`으로 바꾼다. `127.0.0.1`이면 팀원 브라우저는 자기 PC를 가리켜 실패한다.
   변경 후 Expo를 재시작한다.

2. **백엔드 재시작.** `demo-local.ps1 api`는 시작 시점의 LAN IP를 CORS에 넣는다. **네트워크가
   바뀌면 IP도 바뀌므로 반드시 다시 시작**해야 한다.

3. **방화벽 인바운드 허용.** 관리자 PowerShell에서 한 번만:

   ```powershell
   New-NetFirewallRule -DisplayName "helkki demo (api)" -Direction Inbound `
     -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
   New-NetFirewallRule -DisplayName "helkki demo (expo)" -Direction Inbound `
     -LocalPort 8081 -Protocol TCP -Action Allow -Profile Private
   ```

   시연이 끝나면 지운다: `Remove-NetFirewallRule -DisplayName "helkki demo (api)","helkki demo (expo)"`

   `share` 명령이 이 규칙의 유무를 확인해 없으면 위 명령을 그대로 출력한다.

   `-Profile Private`으로 제한한다. 공용 Wi-Fi에서는 열지 않는다.

현재 LAN IP 확인:

```powershell
(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.InterfaceAlias -notmatch 'Loopback|WSL|vEthernet' -and $_.IPAddress -notmatch '^169\.'
} | Select-Object -First 1).IPAddress
```

### 팀원에게 함께 전달할 내용

- 운동 카탈로그는 **합성 데이터이며 도메인 검수를 받지 않았다.** 실제 운동 지도에 쓰면 안 된다.
- 계정은 Firebase 테스트 프로젝트에 실제로 만들어진다. **닉네임과 생년월일에 실제 개인정보를 넣지
  않는다.** 데모 DB는 합성 데이터 전용이다.
- 외부 캘린더 연동과 웨어러블은 미구현이다. 외부 캘린더는 보류 결정됐다(ADR-0010).
- MILD/MODERATE 불편을 선택하면 검수된 규칙이 없어 추천을 만들지 않는다. 의도된 동작이다.

### 인터넷으로 공개하지 않는다

`expo start --tunnel`이나 ngrok으로 외부에 노출하지 않는다. 검수받지 않은 운동 콘텐츠와 개발용
인증 설정이 그대로 공개되고, `CORS_ALLOWED_ORIGINS`와 Firebase 설정도 그 주소에 맞춰 다시 열어야
한다. 원격 팀원과는 화면 공유로 시연한다.

## 10. DB 초기화

```powershell
uv run python -m backend.scripts.demo_seed reset
```

컨테이너까지 버리려면:

```powershell
docker rm -f helkki-demo-pg
```

Firebase 계정은 별도다. 계정까지 지우려면 Firebase 콘솔에서 테스트 사용자를 삭제한다.

## 11. 검증 명령

백엔드:

`TEST_DATABASE_URL`은 반드시 데모 DB가 아닌 `exercise_app_test`를 가리켜야 한다(0.1절). 이름이
`_test`로 끝나지 않으면 통합 테스트가 스스로 실패한다.

```powershell
# 스크래치 DB를 비운 상태에서 시작한다
docker exec helkki-demo-pg psql -U exercise_app -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS exercise_app_test WITH (FORCE);" -c "CREATE DATABASE exercise_app_test OWNER exercise_app;"
$env:TEST_DATABASE_URL = "postgresql+psycopg://exercise_app:local_dev_only@localhost:55432/exercise_app_test"

uv run ruff check backend data/scripts
uv run ruff format --check backend data/scripts
uv run mypy
uv run pytest
```

프론트엔드:

```powershell
cd frontend
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build:production
```

`backend/tests/integration/test_demo_vertical_slice.py`는 실제 PostgreSQL과 실제 FastAPI 스택으로
이 문서의 여정을 그대로 실행한다. `TEST_DATABASE_URL`이 없으면 skip한다.

## 12. 알려진 제약

- 카탈로그가 합성 콘텐츠이므로 추천 결과를 운동 지도에 사용할 수 없다.
- 요청 시간은 10~60분에서 정확히 맞출 수 있다. 그 밖의 값은 서버가 시간을 임의로 바꾸는 대신
  `422 ROUTINE_DURATION_UNAVAILABLE`로 계획을 반환하지 않는다.
- 주간 리포트는 주가 논리적으로 마감된 뒤에만 생성된다. 당일 데모에서는 생성 거부 상태까지만
  확인할 수 있다.
- 다음 주 계획 revision/finalize API는 구현돼 있지만 앱 화면은 아직 없다.
- Calendar와 wearable은 공개 route가 없어 앱에서 호출하지 않는다.
- 소셜 로그인(Kakao/Naver)은 ADR-0009 미승인 예약 계약이라 앱에 노출하지 않는다.
