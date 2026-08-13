# Backend

Python/FastAPI 모듈형 모놀리스 영역입니다.

기반 실행과 검증:

```powershell
uv sync --frozen --group dev
uv run uvicorn backend.app.main:app --reload
uv run pytest
```

설정 예시는 `.env.example`, 전체 로컬 절차는 `docs/LOCAL_DEVELOPMENT.md`를 따릅니다.

예정 계층:

- `app/api/`: HTTP adapter
- `app/core/`: config, logging, common errors
- `app/modules/`: application use case별 모듈
- `app/domain/`: 결정적 규칙과 agent 계약
- `app/db/`: SQLAlchemy model과 repository 구현
- `app/integrations/`: Firebase, social OAuth, 선택적 LLM adapter
- `migrations/`: Alembic revision
- `tests/`: unit, API, integration, golden scenario
