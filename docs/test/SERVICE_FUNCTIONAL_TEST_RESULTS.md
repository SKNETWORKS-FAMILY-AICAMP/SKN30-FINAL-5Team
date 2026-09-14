# 서비스 기능 테스트 결과 보고서

- 실행일: 2026-09-12
- 실행 브랜치/PR: `fix/banana-rewards-and-workout-ux` / PR `#331`
- 대상: 인증부터 주간 리포트·다음 주 계획까지의 MVP 사용자 흐름
- 결과 기준: 실제 실행한 자동화·CI·staging 확인만 `통과`로 표시하고, 현재 배포 범위 밖의 네이티브 검증은 `배포 범위 외`로 분리

## 1. 최종 판정

**현재 배포 대상인 AWS 웹 서비스는 안전성, 핵심 사용자 흐름, 실제 PostgreSQL 통합, Firebase 재로그인, TLS·인증·CORS와 최소 동시 요청 검증을 모두 통과했다. 따라서 MVP 웹 서비스 배포 판정은 `통과`로 한다. 멀티에이전트의 Single-Agent+RAG 대비 비교 우위는 이번 평가에서 입증되지 않았으며, 이는 서비스 배포 판정과 별개다.**

이 판정에서 서비스 배포 가능성과 멀티에이전트 아키텍처의 우월성은 별개다. PR CI는 실제 PostgreSQL 16에서 전체 백엔드 2,441건과 migration round trip, V1·V2 release-flow를 통과했다. 프론트엔드는 45개 suite 736건과 Android/iOS production export를 통과했다. AWS staging에서는 Google OAuth 재로그인 후 기존 프로필·주간 기록이 복구되는 실제 인증·API·Aurora 연결을 확인했다.

## 2. 테스트 범위

이번 보강 평가는 로그인 화면과 인증 경계, 온보딩, 기본 루틴, 일일 체크인, 오늘의 계획, 운동 실행·안전 중단·피드백, 주간 리포트, 다음 주 계획, 계정 삭제 계약을 대상으로 했다. 프론트엔드 테스트는 Firebase/API를 mock 또는 adapter 경계에서 검증하고, 백엔드 API 테스트는 FastAPI HTTP 요청·응답과 서비스 위임을 검증한다.

AWS staging에서는 실제 Aurora PostgreSQL과 Firebase Admin 설정을 확인하고 Google OAuth 로그아웃·재로그인, 프로필·루틴·주간 집계·운동 블록 조회를 실행했다. 운영성 `helkki_staging` DB에는 파괴적인 테스트를 실행하지 않았고, 동일 PR의 GitHub Actions가 독립 PostgreSQL 16 test DB에서 전체 integration과 migration을 수행했다. 현재 배포 대상은 AWS 웹앱이며 Android/iOS 네이티브 앱의 스토어 출시는 별도 승인 범위다.

## 3. 용어

| 용어 | 서비스 관점 설명 |
|---|---|
| 안전 대체 계획(fallback) | AI가 계획을 만들지 못하거나 검증에 실패했을 때 규칙으로 만드는 안전한 대체 계획 |
| held-out | 개선 과정에서 보지 않고 마지막 검증에만 사용한 별도 데이터 |
| Recall@k | 정답 운동이 검색 상위 k개 안에 포함된 비율 |
| MRR | 첫 정답이 검색 결과의 앞쪽에 나올수록 높아지는 순위 지표 |
| P50 / P95 | 요청의 50% / 95%가 이 시간 안에 끝났다는 응답시간 값 |
| LLM Plan Rate | AI가 직접 작성한 계획을 전달한 비율. 규칙 기반 안전 대체 계획은 제외 |
| Constraint Satisfaction | 시간·장비·통증·금기 등 필수 조건을 모두 지킨 비율 |
| Workflow Completion | 추천 절차가 오류 없이 종료 상태에 도달한 비율 |

## 4. 사용자 흐름 기반 기능 테스트

판정은 `통과`, `부분 통과`, `실패`, `미실행`, `배포 범위 외`로 구분한다. `부분 통과`는 코드와 mock 기반 자동화는 통과했지만 필요한 외부 시스템 또는 DB까지 연결하지 못한 경우다.

| ID | 테스트 항목 | 입력 조건 | 기대 결과 | 실제 결과 | 판정 |
|---|---|---|---|---|:--:|
| SF-01 | 로그인·인증 성공/실패 | 유효 토큰, 토큰 없음, 잘못된 토큰, 비활성 계정 | 유효 사용자만 내부 user ID로 통과하고 나머지는 공통 오류로 차단 | 자동화 통과. staging Google OAuth 재로그인과 기존 사용자 복구 성공, 토큰 없음은 `AUTHENTICATION_REQUIRED`, 잘못된 토큰은 `INVALID_TOKEN` 401 확인 | 통과 |
| SF-02 | 권한 없는 접근 | 다른 사용자의 운동 기록 조회, 삭제 대기 계정의 일반 API 접근 | 소유자 범위 밖 데이터와 삭제 대기 계정 접근 차단 | owner scope, 비활성·삭제 대기 계정 차단 API 테스트 통과 | 통과 |
| SF-03 | 온보딩 정보 저장 | 필수 약관·프로필·생년월일·timezone의 정상/누락/경계 입력 | 정상 입력 저장, 누락·잘못된 값 거부, 민감값 오류 응답 비반사 | PostgreSQL vertical slice의 저장·재조회와 staging 재로그인 후 기존 프로필 복구 확인 | 통과 |
| SF-04 | 기본 루틴 생성 | 승인 카탈로그와 정상 프로필, 같은 idempotency key 재요청, 카탈로그 누락 | 루틴 1건 생성·재조회, 중복 생성 방지, 카탈로그 없으면 fail-closed | PostgreSQL vertical slice와 routine API/service 통과, staging 홈에서 최종 루틴과 블록 조회 성공 | 통과 |
| SF-05 | 일일 컨디션 입력 | 피로·수면·회복·통증 부위/강도·red flag·장소·요청 시간 | 필수 안전 입력이 있을 때만 저장하고 같은 날짜 문맥을 일관되게 사용 | daily context API/service와 Home 체크인 화면 테스트 통과 | 통과 |
| SF-06 | 오늘의 운동 계획 생성 | 건강 상태, 제한 시간, 장비, 통증, wearable 없음 | 하나의 최종 계획 또는 명시적 차단/휴식 결과 반환; 수동 입력 fallback 지원 | decision API와 골든 안전 시나리오 통과. 실 LLM 품질 수치는 기존 held-out 결과 사용 | 통과 |
| SF-07 | 운동 시작 | 선택 가능한 최종 루틴, REST 선택, safety veto 계획 | 루틴 선택 시 PLANNED 세션 생성, REST는 세션 미생성, veto 계획은 시작 불가 | workout API/service와 화면 테스트 통과 | 통과 |
| SF-08 | 운동 블록 완료 | RUNNING 세션에서 블록별 완료, 마지막 블록 완료, 응답 유실 후 재조회 | 명시한 블록만 공식 완료되고 마지막 블록 뒤 종료; 재요청에도 중복 반영 없음 | 자동화 통과. staging 운동 캘린더에서 완료 세션과 저장된 10/10 블록 상세 조회 성공 | 통과 |
| SF-09 | 운동 중 안전 이상 반응 | 통증/안전 중단 사유 선택, 증상 원문 미입력 | 세션 중단·재개 차단, 진단 없이 serious tone 안내, 최소 코드만 저장 | API/service·골든·화면 테스트 통과; 원시 증상 상세를 받지 않는 계약 확인 | 통과 |
| SF-10 | 운동 종료 및 피드백 | 완료·부분 수행·미수행·안전 중단 후 난이도와 사유 제출 | 공식 상태와 피드백 저장, 다음 계획 학습 신호로 사용, skip 불이익 없음 | 백엔드 계약과 전용 결과 화면 통과. 완료 블록 0개의 일반 중단은 세션을 종료하지 않고 홈에서 이어하기를 유지하도록 통합 테스트 정정 후 통과 | 통과 |
| SF-11 | 주간 리포트 조회·생성 | 종료된 주, 열린 주, 기존 리포트, 과거 주 | 종료된 주만 생성/조회하고 6개 블록과 안전 중단을 구분해 표시 | 자동화 통과. staging 운동 캘린더에서 완료 3회·휴식 1회 주간 집계와 날짜별 기록 조회 성공 | 통과 |
| SF-12 | 리포트 자동 확인 처리 | 리포트 상세 로드 성공, acknowledgement 응답 유실/실패 | 별도 확인 버튼 없이 자동 저장하고 같은 key로 재시도; 화면은 읽을 수 있음 | API endpoint와 WeeklyReportScreen 재시도·중복 방지 테스트 통과 | 통과 |
| SF-13 | 다음 주 계획 확정 | 직전 리포트 ACKNOWLEDGED/미확인, AI·사용자 수정, AI 수정 횟수 초과 | 확인 전 확정 금지, 확인 후 안전한 계획만 확정, 수정 횟수 제한 | weekly plan API/service·golden과 실제 PostgreSQL vertical slice transaction 통과 | 통과 |
| SF-14 | 중복 요청·연속 클릭·네트워크 오류 | 같은/different payload의 idempotency key 재사용, 응답 유실, 900ms 연속 요청, 네트워크 실패 | 동일 의도는 재생, 다른 payload는 충돌, 버튼 잠금/재시도 안내 | API idempotency와 프론트 재시도·중복 클릭 테스트 통과 | 통과 |
| SF-15 | 계정 삭제와 개인정보 처리 | 최초·반복 삭제, provider 실패, 삭제 대기 계정, 로그/LLM payload 검사 | 즉시 접근 차단, 반복 요청 멱등, 식별정보·원시 건강정보 비노출, 삭제 lifecycle 유지 | 실제 PostgreSQL을 사용하는 전체 CI와 API·golden·privacy 계약 통과. provider 해제·backup 만료는 비동기 운영 lifecycle로 별도 추적 | 통과 |

요약: MVP 웹 서비스 핵심 흐름 15개 모두 `통과`, `실패` 0개다.

## 5. 비기능·일반 서비스 검증

| 항목 | 결과 | 판정 |
|---|---|:--:|
| 잘못된 인증정보·권한 없는 접근 | 인증 및 owner-scope API 자동화 통과 | 통과 |
| 중복 요청·연속 클릭 | mutation idempotency, lost response 재조회, reroll 잠금 자동화 통과 | 통과 |
| 네트워크 지연·중단 안내 | 로그인·Home·리포트·세션 retry/error 상태 자동화 통과. staging 실제 중단 주입은 미실행 | 통과 |
| 데이터 저장 실패 | 실제 PostgreSQL CI와 repository/provider 실패의 안전 오류 매핑 통과 | 통과 |
| Android/iOS 번들 | Expo production export로 양 플랫폼 bundle 생성 성공 | 통과 |
| Android 실제 기기·글자 잘림·버튼 동작 | production bundle은 통과. 네이티브 앱 스토어 출시 전 별도 실기기 승인 대상 | 배포 범위 외 |
| 개인정보 로그·모델 입력 최소화 | LLM privacy, auth safe-error, safety-event 최소 입력 자동화 통과 | 통과 |
| 동시 요청·최소 부하 | staging readiness 동시 50건이 398ms에 50/50 HTTP 200(약 125.46 req/s) | 통과 |
| 계정 삭제 | 실제 PostgreSQL CI와 도메인/API 계약 통과; 외부 provider·backup 완료는 운영 lifecycle 모니터링 대상 | 통과 |

## 6. 실행 결과 요약

| 실행 묶음 | 결과 | 해석 |
|---|---:|---|
| 백엔드 API 전체 | **303 passed** | FastAPI HTTP 계약, 인증, 온보딩, 루틴, 체크인, 결정, 운동, 주간 기능 포함 |
| 핵심 서비스·골든·개인정보 | **160 passed** | 인증·안전·운동·주간 정책과 LLM 입력 최소화 |
| 백엔드 전체 CI | **2,441 passed, 3 intentional skipped** | PostgreSQL integration 포함. skip 3건은 plan 없는 Judge 2건과 별도 Qdrant server 환경 1건 |
| PostgreSQL release gate | **통과** | migration round trip, V1 vertical slice, V2 release flow 통과 |
| 프론트 핵심 화면 | **243 passed** | 인증, Home, 운동, 피드백, 리포트, API retry 중심 10 suites |
| 프론트 전체 회귀 | **736 passed** | 45 suites 전체 통과, 수정 전 실패 2건 해소 |
| Python 품질 게이트 | **통과** | Ruff lint, Ruff format check, mypy |
| 프론트 품질 게이트 | **통과** | Prettier check, ESLint, TypeScript |
| 모바일 production export | **통과** | Android/iOS Hermes bundle 생성 |

백엔드 전체 2,444건도 한 번 실행했으나, 일부 파일 권한을 의도적으로 바꾸는 `tmp_path` 기반
테스트와 Windows 샌드박스가 충돌해 다수 setup error 및 pytest 종료 오류가 발생했다. 이 실행은
제품 실패나 통과 건수로 집계하지 않았고, 임시 디렉터리에 의존하지 않는 위 세 묶음을 분리
재실행해 보고 수치로 사용했다.

## 7. 발견된 결함과 차단 요소

### F-01. 운동 중단 후 피드백 화면 전환 회귀 — 수정 완료

- 위치: `frontend/tests/PreviewGallery.test.tsx:1140`
- 원인: 운동 블록을 하나도 완료하지 않은 일반 중단은 세션을 종료하지 않고 홈으로 돌아가 재개 상태를 보존하는 `STOPPED_RESUMABLE` 계약이다. 기존 preview 테스트가 종료 세션의 피드백 화면을 기대하고 있었다.
- 수정: 테스트를 실제 계약에 맞춰 피드백 입력을 제거하고 홈 복귀와 재개 가능 흐름을 검증하도록 변경했다.
- 검증: 관련 2개 suite 128/128 통과, 프론트 전체 736/736 통과
- 제품 영향: 제품 코드나 공개 계약은 변경하지 않았다.

### F-02. 온보딩 생년월일 wheel animation 회귀 — 수정 완료

- 위치: `frontend/tests/demoFlow.test.tsx:2741`
- 원인: 기존 검증이 서로 다른 연·월·일 `ScrollView`의 요청을 y 좌표만으로 비교했다. 연도를 바꾸면서 월·일 범위가 재정렬될 때 다른 wheel의 정상적인 non-animated 요청을 중복 요청으로 오판했다.
- 수정: animated 요청이 발생한 동일 `ScrollView` 인스턴스 안에서만 같은 위치의 non-animated 요청 여부를 비교하도록 테스트를 좁혔다.
- 검증: 관련 2개 suite 128/128 통과, 프론트 전체 736/736 통과
- 제품 영향: 제품 코드나 접근성 동작은 변경하지 않았다.

### E-01. PostgreSQL 통합 환경 — 해소

AWS staging API의 Aurora `helkki_staging` 연결을 확인했다. 운영 DB 보호를 위해 그 DB에는 schema reset을 실행하지 않았으며, PR #331의 독립 PostgreSQL 16 CI에서 전체 백엔드 2,441건, migration round trip, V1 vertical slice와 V2 release flow를 모두 통과해 배포 gate를 충족했다.

### E-02. 실제 인증 환경 — 해소

staging의 Firebase project ID와 Admin credential 주입을 확인하고, Google OAuth 로그아웃·재로그인 후 기존 프로필과 주간 운동 데이터가 정상 복구되는 것을 확인했다. 이메일·Kakao 경계는 자동화 계약으로 검증했다. Android 네이티브 실기기 검증은 현재 AWS 웹 배포 범위가 아니라 별도 출시 gate로 분리한다.

### T-02. 배포 웹 콘솔 경고

실서비스 브라우저 콘솔에서 Tailwind CDN의 production 사용 경고와 React Native Web의 native animation module 부재에 따른 JS animation fallback 경고가 각각 확인됐다. 주요 화면 로드와 조작은 성공했지만, landing 정적 CSS 빌드 전환과 web animation 설정 정리가 필요하다.

### T-03. 웹 보안 응답 헤더 보완 필요

`www.helkki.com/app-entry.html`과 `app.helkki.com/`은 TLS와 `Cache-Control: no-store`로 정상 응답했지만 `Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`가 없었다. 앱이 iframe으로 제공되므로 `X-Frame-Options`나 CSP는 현재 frame 구조를 고려해 설계해야 한다. 이번 검증에서는 배포 구성을 임의 변경하지 않고 보안 헤더 추가를 후속 배포 항목으로 남겼다.

### T-01. 비동기 화면 테스트 경고

통과한 일부 React Native 테스트에서 state update가 `act(...)`로 감싸지지 않았다는 경고가
출력됐다. 현재 assertion 실패는 아니지만 비동기 타이밍에 따라 테스트가 불안정해질 수 있어
테스트 하네스 개선 대상으로 남긴다.

## 8. 테스트 근거 자료

| 실행일 | 데이터/범위 | 반복 | 결과 또는 위치 | 환경 | 담당자 확인 |
|---|---|---:|---|---|---|
| 2026-09-12 | 백엔드 API 전체 | 1회 | `backend/tests/api` — 303 passed | Windows, Python 3.12.13, pytest 9.1.1 | 자동 실행 확인, 별도 reviewer 미확인 |
| 2026-09-12 | 핵심 서비스·골든·privacy | 1회 | `backend/tests/scenarios`, 선택 unit — 160 passed | Windows, Python 3.12.13 | 자동 실행 확인, 별도 reviewer 미확인 |
| 2026-09-12 | PR 전체 백엔드 CI | 1회 | **2,441 passed, 3 intentional skipped** | GitHub Actions, PostgreSQL 16 test DB | quality-and-test 성공 |
| 2026-09-12 | PostgreSQL release gate | 1회 | migration round trip, V1·V2 release-flow 성공 | 독립 PostgreSQL 16 test DB | CI 3개 backend job 성공 |
| 2026-09-12 | 프론트 핵심 기능 10 suites | 1회 | `frontend/tests` — 243 passed | Node 24.17.0, npm 11.13.0, Jest | 자동 실행 확인, 별도 reviewer 미확인 |
| 2026-09-12 | 프론트 전체 45 suites | 수정 전·후 각 1회 | 수정 전 734 passed, 2 failed → 수정 후 **736 passed** | Node 24.17.0, Jest | 자동 실행 확인, 별도 reviewer 미확인 |
| 2026-09-12 | 프론트 결함 관련 2 suites | 수정 전·후 각 1회 | 수정 전 126 passed, 2 failed → 수정 후 **128 passed** | 동일 환경, 단독 재현·재검증 | 자동 실행 확인, 별도 reviewer 미확인 |
| 2026-09-12 | 정적 품질 검사 | 1회 | Ruff 823 files, mypy 219 files, Prettier/ESLint/tsc 통과 | 로컬 개발 환경 | 자동 실행 확인, 별도 reviewer 미확인 |
| 2026-09-12 | Android/iOS production export | 1회 | `frontend/dist/android`, `frontend/dist/ios` 생성 | Expo 57, Hermes | 자동 실행 확인, 실기기 미확인 |
| 2026-09-12 | AWS staging 인프라·runtime | 1회 | EC2/SSM Online, API·Caddy·PostgreSQL·Qdrant healthy, Aurora `helkki_staging`, Firebase 설정 확인 | AWS ap-northeast-2, release `998c1e1` | 값 비노출 읽기 전용 확인 |
| 2026-09-12 | 공개 API 보안 경계 | 1회 | live/ready 200, 무토큰·잘못된 토큰 401, 허용 CORS 200, 비허용 CORS 400 | `https://www.helkki.com/api/v1` | 실제 TLS 요청 확인 |
| 2026-09-12 | 로그인된 웹앱 주요 조회 | 1회 | 홈·마이페이지·끼끼의 집·운동 캘린더·저장 운동 10/10 블록 조회 성공 | Chrome, `https://app.helkki.com` | 실제 Firebase 세션·staging API |
| 2026-09-12 | Google OAuth 재로그인 | 1회 | 로그아웃 → Google OAuth → Firebase 인증 → 기존 프로필·주간 기록 복구 성공 | Chrome, AWS staging | 실제 인증 E2E 확인 |
| 2026-09-12 | readiness 최소 동시 부하 | 동시 50건 | 50/50 HTTP 200, 398ms, 약 125.46 req/s | 공개 staging TLS endpoint | health endpoint 한정 |
| 2026-09-12 | 웹 응답 헤더·콘솔 | 1회 | landing/app HTTP 200·no-store, production console 경고 2종, 권장 보안 헤더 일부 누락 | Chrome·HTTPS HEAD | 읽기 전용 확인 |
| 2026-09-11~12 | 멀티에이전트 held-out | 문서별 상이 | `ROUND2_HELDOUT_RESULTS.md`, `results/round2/` | 실제 LLM + 고정 dataset | 기존 산출물, 별도 reviewer 미확인 |

주요 재현 명령:

```powershell
uv run pytest -q backend/tests/api
uv run pytest -q backend/tests/integration
uv run pytest -q backend/tests/scenarios/test_auth_provider_golden.py `
  backend/tests/scenarios/test_safety_golden.py `
  backend/tests/scenarios/test_workout_safety_return_golden.py `
  backend/tests/scenarios/test_weekly_policy_golden.py `
  backend/tests/scenarios/test_account_deletion_golden.py `
  backend/tests/unit/test_daily_context_service.py `
  backend/tests/unit/test_routine_service.py `
  backend/tests/unit/test_workout_service.py `
  backend/tests/unit/test_weekly_report_service.py `
  backend/tests/unit/test_weekly_plan_service.py `
  backend/tests/unit/test_llm_agent_privacy.py
npm test -- --runInBand
npm run format:check
npm run lint
npm run typecheck
npm run build:production
```

## 9. 비차단 후속 개선

1. 네이티브 앱 스토어 출시 전 Android 에뮬레이터·실기기에서 화면 잘림과 터치 동작을 별도 승인한다.
2. 실제 트래픽 확대 전에 인증·DB·멀티에이전트 업무 API 부하 시험과 용량 계획을 수행한다.
3. landing page의 Tailwind CDN과 React Native Web animation fallback 경고를 제거한다.
4. iframe 구조를 보존하는 범위에서 HSTS·nosniff·Referrer-Policy와 CSP를 설계·배포한다.
5. provider 해제와 backup 만료를 계정 삭제 운영 lifecycle에서 지속 확인한다.

## 10. 알려진 한계

- 이번 보강은 기존 자동화의 실행·정리에 집중했으며 제품 코드를 수정하지 않았다.
- Firebase·AWS staging 조회 E2E와 독립 PostgreSQL CI는 서로 다른 환경의 결합 근거다. 운영 DB 보호를 위해 staging schema reset 기반 쓰기 suite는 실행하지 않았다.
- 프론트엔드 테스트는 React Native test renderer 기반으로 실제 GPU, 폰트 렌더링, OS별 터치 차이를 보장하지 않는다.
- readiness 50건은 최소 가용성 확인이며, 업무 API의 정식 용량 시험을 대신하지 않는다. 계정 삭제의 외부 provider/backup 완료는 운영 lifecycle 모니터링 대상이다.
- 멀티에이전트 품질·비용·지연 수치는 `TEST_RESULTS.md`와 `ROUND2_HELDOUT_RESULTS.md`의 기존 고정 결과를 사용했다.
