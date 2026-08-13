from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


class DatabaseManager:
    def __init__(self, database_url: str) -> None:
        self.engine: Engine = create_engine(database_url, pool_pre_ping=True)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    def session(self) -> Iterator[Session]:
        with self._session_factory() as db_session:
            yield db_session

    def readiness_probe(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def dispose(self) -> None:
        self.engine.dispose()
