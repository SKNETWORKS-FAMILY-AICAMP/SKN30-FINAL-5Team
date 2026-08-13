# Migrations

`0001_backend_baseline`은 제품 테이블을 만들지 않는 migration root입니다. 실제 테이블은 승인된 `docs/DATA_MODEL.md` 범위와 기능별 Alembic revision에서 추가합니다.

```powershell
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini downgrade base
```

각 변경은 rollback 또는 문서화한 forward-fix 전략과 PostgreSQL 테스트를 포함해야 합니다.
