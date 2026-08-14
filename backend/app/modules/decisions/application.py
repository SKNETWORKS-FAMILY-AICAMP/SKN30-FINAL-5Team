from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.modules.decisions.ports import DecisionAssembly, DecisionRepositoryPort


class DecisionContextAssembler:
    """Assemble the user-scoped, versioned inputs used by all proposal agents."""

    def __init__(self, repository: DecisionRepositoryPort) -> None:
        self._repository = repository

    def assemble(
        self, session: Session, user_id: UUID, daily_context_id: UUID
    ) -> DecisionAssembly | None:
        return self._repository.assemble(session, user_id, daily_context_id)


__all__ = ["DecisionContextAssembler"]
