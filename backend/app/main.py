from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()



def _close_if_possible(obj):
    close = getattr(obj, "close", None)
    if callable(close):
        close()


def _dispose_db_engine_if_possible():
    try:
        from app.db import session as db_session

        engine = getattr(db_session, "engine", None)
        if engine is not None:
            dispose = getattr(engine, "dispose", None)
            if callable(dispose):
                dispose()
    except Exception:
        # Shutdown cleanup should not block app termination.
        pass


@asynccontextmanager
async def lifespan(app):
    yield

    for import_path, attr_name in [
        ("app.domain.cases.repository", "case_repository"),
        ("app.domain.investigations.repository", "investigation_repository"),
        ("app.domain.verified_claims.service", "verified_claim_service"),
    ]:
        try:
            module = __import__(import_path, fromlist=[attr_name])
            _close_if_possible(getattr(module, attr_name, None))
        except Exception:
            pass

    _dispose_db_engine_if_possible()


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }

from app.api.routes import trust_certificates

app.include_router(trust_certificates.router)
