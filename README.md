# Personalized Exercise Wellness

운동 입문자와 복귀자의 기존 계획을 당일 상태에 맞게 안전하게 조정하는 모바일 MVP 모노레포입니다.

현재 저장소는 **설계·계약 단계**입니다. 애플리케이션 코드, 데이터베이스 마이그레이션, 패키지 잠금 파일, 실행 가능한 Docker 구성은 아직 포함하지 않습니다.

## 먼저 읽을 문서

1. [프로젝트 개요](docs/PROJECT_BRIEF.md)
2. [MVP 범위](docs/MVP_SCOPE.md)
3. [아키텍처](docs/ARCHITECTURE.md)
4. [도메인 규칙](docs/DOMAIN_RULES.md)
5. [API 계약](docs/API_CONTRACT.md)
6. [데이터 모델](docs/DATA_MODEL.md)
7. [구현 계획](docs/IMPLEMENTATION_PLAN.md)
8. [Git 협업 규칙](docs/COLLABORATION_GUIDE.md)

문서의 우선순위와 변경 승인 규칙은 [문서 인덱스](docs/README.md)와 루트 [AGENTS.md](AGENTS.md)를 따릅니다.

## 목표 구조

```text
frontend/   React Native 클라이언트
backend/    FastAPI 모듈형 모놀리스
data/       원천·정규화 운동 데이터와 검증 산출물
infra/      로컬 및 MVP 배포 설정
docs/       제품·기술 계약과 작업 문서
.github/    PR·이슈 협업 템플릿
```

## 현재 단계에서 금지되는 작업

- 승인되지 않은 건강·안전 임계값 구현
- LLM에 안전 판단 위임
- 웨어러블을 필수 흐름으로 만들기
- 마이크로서비스, Kafka, Kubernetes, 벡터 DB를 기본안으로 추가
- 계약 승인 전 애플리케이션 코드나 마이그레이션 작성
