import asyncio
import importlib
import json
from pathlib import Path
from typing import Optional

from config.settings import BASE_DIR
from db import repository as repo
from utils.logger import setup_custom_logger

logger = setup_custom_logger("CrawlerRunner", log_prefix="crawler")

MARKETS_JSON = BASE_DIR / "config" / "markets.json"


def _load_crawler(crawler_key: str):
    """crawler/{key}.py 에서 크롤러 클래스를 동적으로 로드한다."""
    module = importlib.import_module(f"crawler.{crawler_key}")
    class_name = crawler_key.capitalize() + "Crawler"
    return getattr(module, class_name)()


async def run_market(crawler_key: str, category_key: str, keyword: str,
                    market_id: int, category_id: int) -> int:
    """단일 마켓·카테고리 크롤링 실행 → DB 저장 → 저장 건수 반환"""
    try:
        crawler = _load_crawler(crawler_key)
    except (ModuleNotFoundError, AttributeError) as e:
        logger.error(f"[{crawler_key}] 크롤러 로드 실패: {e}")
        return 0

    try:
        products = await crawler.crawl(category_key, keyword)
    except Exception as e:
        logger.error(f"[{crawler_key}] 크롤링 실패: {e}")
        return 0

    saved = 0
    for item in products:
        try:
            product_id = repo.upsert_product(
                market_id=market_id,
                category_id=category_id,
                name=item["name"],
                unit=item.get("unit"),
                product_url=item.get("product_url"),
            )
            repo.insert_price(
                product_id=product_id,
                original_price=item.get("original_price"),
                discount_rate=float(item.get("discount_rate", 0.0)),
                sale_price=int(item["sale_price"]),
            )
            saved += 1
        except Exception as e:
            logger.error(f"[{crawler_key}] 상품 저장 오류 ({item.get('name')}): {e}")

    logger.info(f"[{crawler_key}] '{keyword}' {saved}/{len(products)}건 저장 완료")
    return saved


async def run_all(category_key: str = "vegetable",
                  market_keys: Optional[list[str]] = None) -> dict[str, int]:
    """활성 마켓 전체 크롤링.

    Args:
        category_key: 크롤링할 카테고리 (기본: 'vegetable')
        market_keys: 특정 마켓만 실행할 경우 crawler_key 목록
    Returns:
        {crawler_key: 저장건수} 딕셔너리
    """
    repo.purge_old_prices()

    markets = repo.get_markets(active_only=True)
    if market_keys:
        markets = [m for m in markets if m["crawler_key"] in market_keys]

    category = repo.get_category(category_key)
    if category is None:
        logger.error(f"카테고리 '{category_key}' 가 DB에 없습니다. setup_db.py를 먼저 실행하세요.")
        return {}

    category_id = category["id"]
    keyword = category["search_keyword"] or category["name"]
    logger.info(f"카테고리='{category_key}', 검색어='{keyword}'")

    tasks = {
        m["crawler_key"]: run_market(m["crawler_key"], category_key, keyword, m["id"], category_id)
        for m in markets
    }

    # asyncio.gather로 모든 마켓을 병렬 실행, 한 마켓 실패가 다른 마켓에 영향 없음
    keys = list(tasks.keys())
    coros = list(tasks.values())
    outcomes = await asyncio.gather(*coros, return_exceptions=True)

    results = {}
    for key, outcome in zip(keys, outcomes):
        if isinstance(outcome, Exception):
            logger.error(f"[{key}] 크롤링 예외: {outcome}")
            results[key] = 0
        else:
            results[key] = outcome

    return results


def sync_markets_from_json() -> None:
    """config/markets.json 의 마켓 목록을 DB에 동기화한다."""
    with open(MARKETS_JSON, encoding="utf-8") as f:
        markets = json.load(f)
    for m in markets:
        repo.upsert_market(
            name=m["name"],
            url=m["url"],
            crawler_key=m["crawler_key"],
            is_active=m.get("is_active", True),
            login_required=m.get("login_required", False),
        )
    logger.info(f"마켓 {len(markets)}개 DB 동기화 완료")
