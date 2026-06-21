from app.domain.cases.models import CaseRecord


class CaseRepository:
    def create(self, case: CaseRecord) -> CaseRecord:
        raise NotImplementedError

    def get(self, case_id: str) -> CaseRecord | None:
        raise NotImplementedError

    def update(self, case: CaseRecord) -> CaseRecord:
        raise NotImplementedError

    def list(self) -> list[CaseRecord]:
        raise NotImplementedError


class InMemoryCaseRepository(CaseRepository):
    def __init__(self) -> None:
        self._cases: dict[str, CaseRecord] = {}

    def create(self, case: CaseRecord) -> CaseRecord:
        self._cases[case.case_id] = case
        return case

    def get(self, case_id: str) -> CaseRecord | None:
        return self._cases.get(case_id)

    def update(self, case: CaseRecord) -> CaseRecord:
        self._cases[case.case_id] = case
        return case

    def list(self) -> list[CaseRecord]:
        return list(self._cases.values())


from app.core.config import get_settings

settings = get_settings()

if settings.database_backend.lower().strip() == "postgres":
    from app.domain.cases.postgres_repository import PostgresCaseRepository

    case_repository = PostgresCaseRepository()
else:
    case_repository = InMemoryCaseRepository()
