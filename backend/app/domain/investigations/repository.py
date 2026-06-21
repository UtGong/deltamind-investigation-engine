from app.schemas.api import InvestigationResult


class InvestigationRepository:
    def save(self, result: InvestigationResult) -> InvestigationResult:
        raise NotImplementedError

    def get(self, case_id: str) -> InvestigationResult | None:
        raise NotImplementedError


class InMemoryInvestigationRepository(InvestigationRepository):
    def __init__(self) -> None:
        self._results: dict[str, InvestigationResult] = {}

    def save(self, result: InvestigationResult) -> InvestigationResult:
        self._results[result.case_id] = result
        return result

    def get(self, case_id: str) -> InvestigationResult | None:
        return self._results.get(case_id)


from app.core.config import get_settings

settings = get_settings()

if settings.database_backend.lower().strip() == "postgres":
    from app.domain.investigations.postgres_repository import (
        PostgresInvestigationRepository,
    )

    investigation_repository = PostgresInvestigationRepository()
else:
    investigation_repository = InMemoryInvestigationRepository()
