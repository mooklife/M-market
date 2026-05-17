import asyncio
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from db import repository as repo
from crawler.runner import run_all, sync_markets_from_json
from utils.logger import setup_custom_logger

router = APIRouter(prefix="/api")
logger = setup_custom_logger("API", log_prefix="web")

_crawl_status: dict = {"running": False, "last_result": None}


# ── 카테고리 ──────────────────────────────────────────────────────────────────

@router.get("/categories")
def get_categories():
    return repo.get_categories()


@router.post("/categories/{key}/keyword")
def update_keyword(key: str, keyword: str):
    repo.update_category_keyword(key, keyword)
    return {"ok": True, "key": key, "keyword": keyword}


# ── 마켓 ──────────────────────────────────────────────────────────────────────

@router.get("/markets")
def get_markets():
    return repo.get_markets(active_only=False)


@router.post("/markets/{crawler_key}/toggle")
def toggle_market(crawler_key: str, active: bool):
    repo.set_market_active(crawler_key, active)
    return {"ok": True}


# ── 추적 품목 ─────────────────────────────────────────────────────────────────

@router.get("/items")
def get_items(category: str = Query(default="vegetable"), active_only: bool = Query(default=False)):
    return repo.get_search_items(category, active_only=active_only)


@router.post("/items")
def add_item(category: str = Query(default="vegetable"), name: str = Query(...)):
    if not name.strip():
        raise HTTPException(status_code=400, detail="name 필요")
    item_id = repo.add_search_item(category, name.strip())
    return {"ok": True, "id": item_id, "name": name.strip()}


@router.post("/items/{item_id}/toggle")
def toggle_item(item_id: int, active: bool):
    repo.toggle_search_item(item_id, active)
    return {"ok": True}


@router.delete("/items/{item_id}")
def delete_item(item_id: int):
    repo.delete_search_item(item_id)
    return {"ok": True}


# ── 상품 / 가격 ───────────────────────────────────────────────────────────────

@router.get("/products")
def get_products(category: str = Query(default="vegetable")):
    """품목 × 마켓 최신가 (메인 화면용)"""
    return repo.get_items_with_latest_prices(category)


@router.get("/prices/item/{item_id}")
def get_prices_by_item(item_id: int, days: int = Query(default=90, ge=1, le=365)):
    """품목의 전체 마켓 가격 이력 (추세 차트용)"""
    product_ids = repo.get_product_ids_by_search_item(item_id)
    if not product_ids:
        raise HTTPException(status_code=404, detail="가격 데이터 없음")
    history = repo.get_price_history_multi(product_ids, days=days)
    return {"item_id": item_id, "history": history}


@router.get("/prices/{product_id}")
def get_prices(product_id: int, days: int = Query(default=90, ge=1, le=365)):
    product = repo.get_product_by_id(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")
    history = repo.get_price_history(product_id, days=days)
    return {"product": product, "history": history}


# ── 크롤링 ────────────────────────────────────────────────────────────────────

@router.post("/crawl")
async def trigger_crawl(
    background_tasks: BackgroundTasks,
    category: str = Query(default="vegetable"),
    market_keys: Optional[str] = Query(default=None, description="쉼표 구분, 예: kurly,coupang"),
    item_names: Optional[str] = Query(default=None, description="쉼표 구분, 예: 양파,당근"),
):
    if _crawl_status["running"]:
        return {"ok": False, "message": "이미 크롤링이 진행 중입니다"}

    mkeys = market_keys.split(",") if market_keys else None
    inames = item_names.split(",") if item_names else None
    background_tasks.add_task(_run_crawl_bg, category, mkeys, inames)
    return {"ok": True, "message": f"'{category}' 크롤링을 시작했습니다"}


@router.get("/crawl/status")
def get_crawl_status():
    return _crawl_status


async def _run_crawl_bg(category: str, market_keys: Optional[list[str]],
                        item_names: Optional[list[str]]) -> None:
    _crawl_status["running"] = True
    try:
        result = await run_all(category_key=category, market_keys=market_keys, item_names=item_names)
        _crawl_status["last_result"] = result
        logger.info(f"크롤링 완료: {result}")
    except Exception as e:
        logger.error(f"크롤링 오류: {e}")
        _crawl_status["last_result"] = {"error": str(e)}
    finally:
        _crawl_status["running"] = False
