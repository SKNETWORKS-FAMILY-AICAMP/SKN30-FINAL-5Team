# 헬끼 (helkki)

> 오늘의 몸 상태와 생활 조건을 반영해, 운동 입문자와 복귀자에게 **하나의 안전한 운동 루틴**을 제안하는 개인화 운동 웰니스 서비스입니다.

헬끼는 의료 진단·치료·처방을 제공하지 않습니다. 사용자의 명시적 체크인과 승인된 운동·안전 규칙을 바탕으로 운동 계획을 조정하며, 통증 또는 이상 반응이 있으면 운동을 강요하지 않고 보수적인 상태로 안내합니다.

## Team 콩닥



<table>
  <tr>
    <td align="center" width="25%">
      <img src="assets/team/onion-chae-donghyeon.jpg" width="140" height="140" alt="채동현 캐릭터 이미지" /><br />
      <strong>채동현</strong><br />
      <sub>@chromerao</sub><br />
      <sub>개발 리드 · 데이터</sub><br /><br />
    </td>
    <td align="center" width="25%">
      <img src="assets/team/riceball-kim-beomjung.jpg" width="140" height="140" alt="김범중 캐릭터 이미지" /><br />
      <strong>김범중</strong><br />
      <sub>@bumshark2</sub><br />
      <sub>프론트엔드</sub><br /><br />
    </td>
    <td align="center" width="25%">
      <img src="assets/team/ddonggun-jang-gyuwon.jpg" width="140" height="140" alt="장규원 캐릭터 이미지" /><br />
      <strong>장규원</strong><br />
      <sub>@gyuwon02</sub><br />
      <sub>백엔드</sub><br /><br />
    </td>
    <td align="center" width="25%">
      <img src="assets/team/celery-park-sebin.jpg" width="140" height="140" alt="박세빈 캐릭터 이미지" /><br />
      <strong>박세빈</strong><br />
      <sub>@sebin1030</sub><br />
      <sub>PM · 문서 기획</sub><br /><br />
    </td>
  </tr>
</table>

## 서비스 소개

운동을 다시 시작하려 해도 컨디션, 시간, 장소, 장비가 매일 달라 계획을 지키기 어려울 수 있습니다. 헬끼는 온보딩에서 설정한 목표와 운동 환경을 바탕으로 기본 루틴을 만들고, 당일 체크인과 안전 규칙을 반영해 실행할 루틴을 결정합니다.

- **온보딩과 기본 루틴**: 목표, 경험 수준, 장소·장비, 주의 부위를 반영합니다.
- **당일 컨디션 반영**: 수동 체크인만으로도 이용할 수 있으며, 웨어러블은 필수 조건이 아닙니다.
- **안전 우선 조정**: 결정적 안전 규칙의 veto는 다른 제안이나 LLM이 바꿀 수 없습니다.
- **운동 실행 기록**: 공식 완료 상태는 경과 시간이 아니라 앱에서 각 운동 블록을 완료한 기록으로 판단합니다.
- **주간 회고와 다음 계획**: 주간 리포트를 확인한 뒤 다음 주 계획을 확정합니다.

## 핵심 사용자 흐름

```text
온보딩 → 기본 루틴 생성 → 일일 체크인 → 안전 검토·루틴 결정
   → 운동 블록 실행·피드백 → 주간 리포트 확인 → 다음 주 계획
```

## 구현 현황

현재 `develop`에는 백엔드 핵심 기능과 데이터 영속성 기반이 구현되어 있습니다.

| 영역 | 현재 반영 범위 |
|---|---|
| 인증·프로필 | Firebase ID Token 검증 경계, 내부 사용자 연결, 온보딩·동의 |
| 운동 계획 | 버전형 기본 루틴, 일일 체크인, 다중 제안 및 Coordinator 결정 저장 |
| 운동 실행 | 세션 시작, 운동 블록 완료, 완료·미완료·안전 피드백 |
| 주간 관리 | 주간 리포트 생성·확인, 주간 계획 revision 및 finalize 규칙 |
| 개인정보 | 계정 삭제 요청과 보존 수명주기 기반 |
| 데이터·안전 | 승인 상태가 있는 운동 카탈로그, 결정적 안전·시간·복귀 규칙, golden scenario 테스트 |
| 캘린더 | 외부 컨텍스트 정책, provider 경계, PostgreSQL 영속성 기반 구현 |

아직 별도 작업이 필요한 범위도 명확히 구분합니다.

- 모바일 UI는 React Native 초기 이식 단계이며, 백엔드 API와의 전체 연결은 진행 중입니다.
- Kakao/Naver 소셜 OAuth는 계약과 후속 작업 범위가 정의되어 있으며, 공개 OAuth API 구현은 완료되지 않았습니다.
- Google Calendar 공개 API와 실제 OAuth credential·secret-manager 운영 연결은 아직 완료되지 않았습니다.
- Docker Compose/Dockerfile 기반의 실행 환경은 아직 제공하지 않습니다.

## 기술 구성

| 구분 | 기술 및 원칙 |
|---|---|
| Mobile | React Native, TypeScript, Expo Development Build |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy |
| Database | PostgreSQL, Alembic migration |
| Authentication | Firebase Authentication 및 Firebase ID Token 검증 |
| Quality | Ruff, mypy, pytest, API·통합·golden scenario 테스트 |
| Architecture | 모듈형 모놀리스, 결정적 도메인 규칙, 외부 연동 adapter 경계 |

## 프로젝트 구조

```text
frontend/   React Native 모바일 앱과 화면·컴포넌트·테스트
backend/    FastAPI 모듈형 모놀리스, Alembic migration, API·통합 테스트
data/       원천·정규화 운동 데이터, 검증 도구와 산출물
infra/      로컬·배포 운영 문서와 환경 설정 예시
docs/       제품, 도메인, API, 데이터 계약 및 ADR
```

## 로컬 실행 및 검증

백엔드는 `uv`를 사용합니다. PostgreSQL과 필요한 환경 변수를 준비한 뒤 실행합니다.

```powershell
uv sync --frozen --group dev
Copy-Item backend/.env.example .env
uv run uvicorn backend.app.main:app --reload
```

기본 검증 명령은 다음과 같습니다.

```powershell
uv run ruff check backend data/scripts
uv run ruff format --check backend data/scripts
uv run mypy
uv run pytest
```

자세한 준비 절차는 [로컬 개발 가이드](docs/LOCAL_DEVELOPMENT.md), 백엔드 실행 내용은 [backend README](backend/README.md), 프론트엔드 환경은 [frontend README](frontend/README.md)를 확인하세요.

## 주요 문서

- [프로젝트 개요](docs/PROJECT_BRIEF.md)
- [MVP 범위](docs/MVP_SCOPE.md)
- [아키텍처](docs/ARCHITECTURE.md)
- [도메인 규칙](docs/DOMAIN_RULES.md)
- [API 계약](docs/API_CONTRACT.md)
- [데이터 모델](docs/DATA_MODEL.md)
- [테스트 전략](docs/TEST_STRATEGY.md)
- [ADR 목록](docs/adr/README.md)
- [문서 우선순위 및 변경 규칙](docs/README.md)
