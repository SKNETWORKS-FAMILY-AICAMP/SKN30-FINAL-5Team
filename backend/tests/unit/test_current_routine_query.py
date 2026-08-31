from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from backend.app.db.repositories.routine import RoutineRepository


class _Rows:
    def all(self) -> list[Any]:
        return []


class _CapturingSession:
    statement: Any | None = None

    def scalars(self, statement: Any) -> _Rows:
        self.statement = statement
        return _Rows()


def test_current_routine_query_requires_the_current_production_catalog() -> None:
    session = _CapturingSession()

    result = RoutineRepository().get_current_routine_payload(
        session,  # type: ignore[arg-type]
        uuid4(),
        date(2026, 8, 31),
    )

    assert result is None
    assert session.statement is not None
    sql = str(
        session.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "JOIN catalog_versions" in sql
    assert "catalog_versions.status_code = 'ACTIVE'" in sql
    assert "catalog_versions.review_status_code = 'DOMAIN_APPROVED'" in sql
    assert "catalog_versions.review_method_code = 'DOMAIN_REVIEWER'" in sql
    assert "catalog_versions.status_interpretation_code = 'PRODUCTION_APPROVED'" in sql
    assert "catalog_versions.production_eligible IS true" in sql
    assert "catalog_versions.activated_at IS NOT NULL" in sql
