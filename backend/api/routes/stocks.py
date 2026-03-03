from fastapi import APIRouter, Query

from backend.services.nse import get_nse_stocks, get_nse_stocks_sync, search_stocks

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Search NSE stocks instantly from cache.
    Returns fallback list immediately; full NSE list loads in background.
    """
    # Trigger background refresh if stale — but don't wait for it
    await get_nse_stocks()
    # Return results from whatever is in cache right now
    stocks = get_nse_stocks_sync()
    results = search_stocks(q, stocks, limit=limit)
    return results


@router.get("/status")
async def cache_status():
    """How many stocks are currently in the cache."""
    from backend.services.nse import _cache, _cache_time, _fetch_in_progress
    import time
    return {
        "cached_stocks": len(_cache),
        "fetch_in_progress": _fetch_in_progress,
        "cache_age_seconds": round(time.time() - _cache_time) if _cache_time else None,
    }
