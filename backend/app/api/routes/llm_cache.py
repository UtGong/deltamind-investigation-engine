from fastapi import APIRouter

from app.domain.llm_cache.repository import llm_cache_repository

router = APIRouter(prefix="/llm-cache", tags=["llm-cache"])


@router.get("/stats")
async def get_llm_cache_stats() -> dict:
    return llm_cache_repository.stats()


@router.delete("")
async def clear_llm_cache() -> dict:
    llm_cache_repository.clear()
    return {"cleared": True}
