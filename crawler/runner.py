import asyncio
import importlib
import json
import re
from pathlib import Path
from typing import Optional

from config.settings import BASE_DIR
from db import repository as repo
from utils.logger import setup_custom_logger

logger = setup_custom_logger("CrawlerRunner", log_prefix="crawler")

MARKETS_JSON = BASE_DIR / "config" / "markets.json"

# 가공식품 판별 키워드 — 이 단어가 상품명에 포함되면 실제 야채/과일이 아닌 것으로 간주
# 주의: 짧은 단어(2글자 이하)는 진짜 야채명에도 포함될 수 있어 제외
_PROCESSED_KEYWORDS = [
    "소스", "드레싱", "마요네즈", "케첩", "시즈닝", "양념장",
    "분말", "파우더", "엑기스", "추출물", "진액",
    "즙", "주스", "음료수", "에이드", "스무디",
    "과자", "스낵", "크래커", "팝콘",
    "장아찌", "피클", "짱아찌", "염장",
    "통조림", "동결건조", "건조칩",
    "라면", "파스타", "만두피",
    "식초", "간장", "된장", "고추장", "쌈장",
    "젤리", "캔디", "사탕", "초콜릿",
    "아이스크림", "빙수",
    "크림치즈", "버터",
    "씨앗", "종자",
]


def _is_actual_item(product_name: str, search_item: str) -> bool:
    """상품명을 보고 저장할 상품인지 판별.

    Returns:
        True  → 저장
        False → 제외 (가공품 또는 UI 쓰레기 텍스트)
    """
    # 가격/UI 라벨이 상품명으로 들어온 경우 제거
    import re as _re
    if _re.search(r"\d[\d,]+원", product_name):   # "1,234원" 포함
        return False
    if _re.search(r"\d+[gG][가-힣]당", product_name):  # "10g당"
        return False
    if len(product_name.strip()) < 4:
        return False

    # 가공식품 키워드
    for kw in _PROCESSED_KEYWORDS:
        if kw in product_name:
            return False
    return True


def _load_crawler(crawler_key: str):
    """crawler/{key}.py 에서 크롤러 클래스를 동적으로 로드한다."""
    module = importlib.import_module(f"crawler.{crawler_key}")
    class_name = crawler_key.capitalize() + "Crawler"
    return getattr(module, class_name)()


async def run_market(crawler_key: str, keyword: str, search_item_id: int,
                     market_id: int, category_id: int) -> int:
    """단일 마켓·품목 크롤링 → DB 저장 → 저장 건수 반환"""
    try:
        crawler = _load_crawler(crawler_key)
    except (ModuleNotFoundError, AttributeError) as e:
        logger.error(f"[{crawler_key}] 크롤러 로드 실패: {e}")
        return 0

    try:
        products = await crawler.crawl("vegetable", keyword)
    except Exception as e:
        logger.error(f"[{crawler_key}] '{keyword}' 크롤링 실패: {e}")
        return 0

    # 가공품 필터링
    before = len(products)
    products = [p for p in products if _is_actual_item(p.get("name", ""), keyword)]
    filtered = before - len(products)
    if filtered:
        logger.info(f"[{crawler_key}] '{keyword}' 가공품 {filtered}건 제외")

    saved = 0
    for item in products:
        try:
            product_id = repo.upsert_product(
                market_id=market_id,
                category_id=category_id,
                search_item_id=search_item_id,
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
            logger.error(f"[{crawler_key}] '{keyword}' 상품 저장 오류 ({item.get('name')}): {e}")

    logger.info(f"[{crawler_key}] '{keyword}' {saved}/{len(products)}건 저장")
    return saved


async def run_all(category_key: str = "vegetable",
                  market_keys: Optional[list[str]] = None,
                  item_names: Optional[list[str]] = None) -> dict[str, int]:
    """활성 품목 × 활성 마켓 전체 크롤링.

    Args:
        category_key: 카테고리 키 (기본: 'vegetable')
        market_keys: 특정 마켓만 실행 (None = 전체)
        item_names: 특정 품목만 실행 (None = 전체 활성 품목)
    Returns:
        {crawler_key: 총 저장건수} 딕셔너리
    """
    repo.purge_old_prices()

    category = repo.get_category(category_key)
    if category is None:
        logger.error(f"카테고리 '{category_key}' 가 DB에 없습니다. setup_db.py를 먼저 실행하세요.")
        return {}

    category_id = category["id"]
    markets = repo.get_markets(active_only=True)
    if market_keys:
        markets = [m for m in markets if m["crawler_key"] in market_keys]

    search_items = repo.get_search_items(category_key, active_only=True)
    if item_names:
        search_items = [i for i in search_items if i["name"] in item_names]

    if not search_items:
        logger.warning(f"'{category_key}' 카테고리에 활성 품목이 없습니다. setup_db.py를 실행하세요.")
        return {}

    logger.info(f"카테고리='{category_key}', 품목 {len(search_items)}개, 마켓 {len(markets)}개")

    totals: dict[str, int] = {m["crawler_key"]: 0 for m in markets}

    # 품목별로 순차 실행 (각 품목 내에서는 마켓 병렬)
    for si in search_items:
        logger.info(f"  ▶ '{si['name']}' 크롤링 중...")
        tasks = {
            m["crawler_key"]: run_market(
                m["crawler_key"], si["name"], si["id"], m["id"], category_id
            )
            for m in markets
        }
        keys = list(tasks.keys())
        outcomes = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, outcome in zip(keys, outcomes):
            if isinstance(outcome, Exception):
                logger.error(f"[{key}] '{si['name']}' 예외: {outcome}")
            else:
                totals[key] = totals.get(key, 0) + (outcome or 0)

    return totals


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
