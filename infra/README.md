# Infrastructure

로컬 Docker와 MVP 배포 설정의 소유 영역입니다. Issue #149 승인으로 API, PostgreSQL, Qdrant의
로컬 개발용 Compose만 제공하며 production 배포 설정은 계속 보류합니다.

- `docker/`: API, PostgreSQL, Qdrant 로컬 구성과 검증 runbook
- `deployment/`: 선택한 플랫폼의 배포 선언과 운영 runbook

Kubernetes, Redis, worker, queue는 기본 구조가 아닙니다.

Compose는 migration, catalog import 또는 activation을 API startup에 포함하지 않습니다. 실제 실행은
`docker/README.md`의 명시적 one-shot 순서를 따릅니다.
