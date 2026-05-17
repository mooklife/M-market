"""수동 크롤링 실행 스크립트

사용법:
    python scripts/crawl.py                          # 야채 전체 마켓
    python scripts/crawl.py --category vegetable     # 카테고리 지정
    python scripts/crawl.py --market kurly,coupang   # 특정 마켓만
    python scripts/crawl.py --category fruit --market kurly
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import init_db
from crawler.runner import run_all, sync_markets_from_json
from utils.logger import setup_custom_logger

logger = setup_custom_logger("CrawlScript", log_prefix="crawler")


async def main(category: str, market_keys: list[str] | None) -> None:
    init_db()
    sync_markets_from_json()

    logger.info(f"크롤링 시작 — category={category}, markets={market_keys or 'ALL'}")
    results = await run_all(category_key=category, market_keys=market_keys)

    total = sum(results.values())
    logger.info(f"크롤링 완료 — 총 {total}건")
    for key, count in results.items():
        logger.info(f"  {key}: {count}건")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="M-Market 크롤러")
    parser.add_argument("--category", default="vegetable", help="카테고리 키 (vegetable/fruit/grocery)")
    parser.add_argument("--market", default=None, help="마켓 키 (쉼표 구분, 예: kurly,coupang)")
    args = parser.parse_args()

    market_keys = [k.strip() for k in args.market.split(",")] if args.market else None
    asyncio.run(main(args.category, market_keys))
