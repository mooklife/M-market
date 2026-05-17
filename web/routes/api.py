import asyncio
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from db import repository as repo
from crawler.runner import run_all, sync_markets_from_json
from utils.logger import setup_custom_logger

router = APIRouter(prefix="/api")
logger = setup_custom_logger("API", log_prefix="web")

_crawl_status: dict = {"running": False, "last_result": None}


@router.get("/categories")
def get_categories():
    return repo.get_categories()


@router.get("/markets")
def get_markets():
    return repo.get_markets(active_only=False)


@router.post("/markets/{crawler_key}/toggle")
def toggle_market(crawler_key: str, active: bool):
    repo.set_market_active(crawler_key, active)
    return {"ok": True}


@router.get("/products")
def get_products(category: str = Query(default="vegetable")):
    """카테고리별 상품 목록 — 마켓별 최신 판매가 포함"""
    products = repo.get_products_by_category(category)

    # 품목명으로 그룹핑 (UI에서 동일 야채를 마켓별로 비교)
    grouped: dict[str, list] = {}
    for p in products:
        key = p["name"]
        grouped.setdefault(key, []).append(p)

    return [
        {"name": name, "markets": items}
        for name, items in sorted(grouped.items())
    ]


@router.get("/prices/{product_id}")
def get_prices(product_id: int, days: int = Query(default=90, ge=1, le=365)):
    product = repo.get_product_by_id(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")
    history = repo.get_price_history(product_id, days=days)
    return {"product": product, "history": history}


@router.get("/prices/compare/{product_name}")
def get_prices_compare(
    product_name: str,
    category: str = Query(default="vegetable"),
    days: int = Query(default=90, ge=1, le=365),
):
    """같은 이름의 상품을 여러 마켓에서 비교 (추세 차트용)"""
    all_products = repo.get_products_by_category(category)
    matched = [p for p in all_products if p["name"] == product_name]
    if not matched:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")

    product_ids = list({p["id"] for p in matched})
    history = repo.get_price_history_multi(product_ids, days=days)
    return {"product_name": product_name, "markets": matched, "history": history}


@router.post("/crawl")
async def trigger_crawl(
    background_tasks: BackgroundTasks,
    category: str = Query(default="vegetable"),
    market_keys: Optional[str] = Query(default=None, description="쉼표 구분, 예: kurly,coupang"),
):
    """수동 크롤링 트리거 — 백그라운드 실행"""
    if _crawl_status["running"]:
        return {"ok": False, "message": "이미 크롤링이 진행 중입니다"}

    keys = market_keys.split(",") if market_keys else None
    background_tasks.add_task(_run_crawl_bg, category, keys)
    return {"ok": True, "message": f"'{category}' 크롤링을 시작했습니다"}


@router.get("/crawl/status")
def get_crawl_status():
    return _crawl_status


async def _run_crawl_bg(category: str, market_keys: Optional[list[str]]) -> None:
    _crawl_status["running"] = True
    try:
        result = await run_all(category_key=category, market_keys=market_keys)
        _crawl_status["last_result"] = result
        logger.info(f"크롤링 완료: {result}")
    except Exception as e:
        logger.error(f"크롤링 오류: {e}")
        _crawl_status["last_result"] = {"error": str(e)}
    finally:
        _crawl_status["running"] = False
