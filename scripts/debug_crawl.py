"""크롤러 디버그 스크립트 — 실제 HTML 구조와 셀렉터를 확인한다.

사용법:
    python scripts/debug_crawl.py --market kurly
    python scripts/debug_crawl.py --market oasis
    python scripts/debug_crawl.py --market all
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

SEARCH_URLS = {
    "kurly":   "https://www.kurly.com/search?sword=야채",
    "coupang": "https://www.coupang.com/np/search?q=야채&channel=user",
    "emart":   "https://emart.ssg.com/search/searchGate.ssg?query=야채",
    "lotte":   "https://www.lotteon.com/p/search?q=야채&mall_tp=PO",
    "oasis":   "https://www.oasis.co.kr/search?query=야채",
}

DEBUG_DIR = Path(__file__).parent.parent / "data" / "debug"


async def inspect_market(market: str) -> None:
    url = SEARCH_URLS[market]
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"[{market}] {url}")
    print('='*60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)  # JS 렌더링 대기

        # 스크린샷 저장
        screenshot_path = DEBUG_DIR / f"{market}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"  스크린샷: {screenshot_path}")

        # 상품 카드로 추정되는 요소 탐색
        print("\n  [상품 카드 후보 셀렉터 탐색]")
        candidate_selectors = [
            # 일반적인 상품 목록 패턴
            "ul[class*='product'] > li",
            "ul[class*='Product'] > li",
            "ul[class*='item'] > li",
            "ul[class*='goods'] > li",
            ".product-list li",
            ".goods-list li",
            "[class*='ProductCard']",
            "[class*='product-card']",
            "[class*='product_card']",
            "[class*='ItemCard']",
            "[class*='item-card']",
            "[class*='GoodsItem']",
            "[class*='goods-item']",
            "[class*='goods_item']",
            "li[class*='product']",
            "li[class*='goods']",
            "li[class*='item']",
            "article[class*='product']",
            "article[class*='goods']",
        ]
        for sel in candidate_selectors:
            count = await page.locator(sel).count()
            if count > 0:
                print(f"    ✅ {count:3d}개 — {sel}")

        # 가격 요소 탐색
        print("\n  [가격 요소 후보 셀렉터 탐색]")
        price_selectors = [
            "[class*='price']",
            "[class*='Price']",
            "[class*='원']",
            "strong[class*='price']",
            "span[class*='price']",
            "em[class*='price']",
        ]
        for sel in price_selectors:
            count = await page.locator(sel).count()
            if count > 0:
                # 첫 번째 요소의 텍스트 샘플
                sample = await page.locator(sel).first.inner_text()
                print(f"    ✅ {count:3d}개 — {sel}  (예: '{sample[:30].strip()}')")

        # 실제 첫 번째 상품 카드 HTML 출력 (가장 긴 li 요소)
        print("\n  [첫 번째 상품 카드 HTML 샘플 (li 요소 기준)]")
        li_elements = page.locator("li")
        li_count = await li_elements.count()
        longest_html = ""
        for i in range(min(li_count, 30)):
            html = await li_elements.nth(i).inner_html()
            if len(html) > len(longest_html) and "원" in html:
                longest_html = html
        if longest_html:
            print(f"    길이: {len(longest_html)}자")
            print(f"    HTML:\n{longest_html[:1500]}")
        else:
            print("    '원' 텍스트를 포함한 li 요소 없음")

        await browser.close()


async def main(market: str) -> None:
    targets = list(SEARCH_URLS.keys()) if market == "all" else [market]
    for t in targets:
        await inspect_market(t)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="크롤러 디버그")
    parser.add_argument("--market", default="oasis",
                        choices=list(SEARCH_URLS.keys()) + ["all"],
                        help="확인할 마켓 키")
    args = parser.parse_args()
    asyncio.run(main(args.market))
