# Backend

Python/FastAPI 모듈형 모놀리스 영역입니다. 아직 실행 코드나 패키지는 생성하지 않았습니다.

예정 계층:

- `app/api/`: HTTP adapter
- `app/core/`: config, logging, common errors
- `app/modules/`: application use case별 모듈
- `app/domain/`: 결정적 규칙과 agent 계약
- `app/db/`: SQLAlchemy model과 repository 구현
- `app/integrations/`: Firebase, social OAuth, 선택적 LLM adapter
- `migrations/`: Alembic revision
- `tests/`: unit, API, integration, golden scenario
