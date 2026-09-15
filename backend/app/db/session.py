from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_LOCK_TIMEOUT_MS = 120_000


def _connect_args(lock_timeout_ms: int) -> dict[str, str]:
    """Bound every lock wait taken on a pooled connection.

    Advisory locks and `FOR UPDATE` both wait forever by default, so a holder
    that never commits wedges the waiter's connection permanently. Setting the
    ceiling here rather than at each call site covers every repository lock,
    including the ones an async request path acquires.
    """

    if lock_timeout_ms < 0:
        raise ValueError("lock_timeout_ms must not be negative")
    return {"options": f"-c lock_timeout={lock_timeout_ms}"}


class DatabaseManager:
    def __init__(
        self,
        database_url: str,
        *,
        lock_timeout_ms: int = DEFAULT_LOCK_TIMEOUT_MS,
    ) -> None:
        self.engine: Engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args=_connect_args(lock_timeout_ms),
        )
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    def session(self) -> Iterator[Session]:
        with self._session_factory() as db_session:
            yield db_session

    def new_session(self) -> Session:
        """Return an owned session for application Unit-of-Work adapters."""

        return self._session_factory()

    def readiness_probe(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def dispose(self) -> None:
        self.engine.dispose()
