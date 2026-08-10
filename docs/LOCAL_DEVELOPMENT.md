# LOCAL_DEVELOPMENT.md

## 1. 결정

로컬 개발은 프론트엔드 개발 서버, FastAPI, PostgreSQL을 최소 구성으로 한다. Redis, worker, scheduler, wearable, LLM은 필수가 아니다.

예정 실행 형태:

```text
host: React Native / Expo Development Build
container or host: FastAPI
container: PostgreSQL
optional adapter stub: Firebase, social OAuth, LLM
```

실행 가능한 `docker-compose.yml`, Dockerfile, `.env.example`, 패키지 파일은 기반 구현 PR에서 실제 설정 키가 승인된 후 작성한다.

## 2. 환경 구분

- `local`: 합성 데이터, provider emulator 또는 test project
- `test`: 자동 테스트용 격리 DB
- `staging`: 모바일 통합과 데모
- `production`: 파일럿 승인 후

환경별 secret과 DB를 공유하지 않는다.

## 3. 예상 환경 변수 범주

값이나 secret 자체는 문서·저장소에 쓰지 않는다.

- application environment와 log level
- PostgreSQL connection
- Firebase project/credential reference
- Kakao/Naver OAuth client reference
- 선택적 LLM provider reference
- CORS/allowed client 설정

정확한 키 이름은 config schema와 함께 결정한다.

## 4. 개발 데이터

- 운동 카탈로그는 승인 상태가 명시된 seed를 사용한다.
- 합성 사용자와 합성 체크인만 사용한다.
- 로컬에서 실제 provider token과 건강 데이터를 공유하지 않는다.
- raw/normalized/generated 데이터 경계를 유지한다.

## 5. 권장 시작 순서

구현 후의 목표 순서는 다음과 같다.

1. 환경 변수 검증
2. PostgreSQL 기동과 readiness
3. migration 적용
4. 승인 seed 로드
5. FastAPI readiness 확인
6. 모바일 앱 API 연결

## 6. 대안과 선택 이유

전체 스택을 Kubernetes로 로컬 실행하지 않는다. 초기 서비스 수와 팀 규모에 비해 유지 비용이 크다. Firebase·소셜·LLM의 실제 외부 연결을 모든 개발자에게 강제하지 않고 adapter stub/test project를 허용한다.

## 7. 아직 확정되지 않은 사항과 질문

- Python 패키지 도구를 `uv`로 확정할지
- Node 패키지 도구와 버전
- PostgreSQL 지원 버전
- Android/iOS 로컬 개발의 최소 OS·SDK 버전
- staging 계정과 secret 관리 담당자
