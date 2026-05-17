import re
from typing import Optional

from playwright.async_api import Page

from crawler.base import BaseCrawler


class KurlyCrawler(BaseCrawler):
    market_key = "kurly"
    category_url = {
        "vegetable": "https://www.kurly.com/categories/882",  # 채소
        "fruit":     "https://www.kurly.com/categories/883",  # 과일
        "grocery":   "https://www.kurly.com/categories/891",  # 간편식품
    }

    async def _fetch_products(self, page: Page, url: str) -> list[dict]:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        await page.wait_for_selector("li[class*='css-']", timeout=15000)

        # 스크롤 다운해 더 많은 상품 로드
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(1000)

        items = await page.query_selector_all("li[data-testid='productList-item']")
        if not items:
            # fallback: 일반적인 상품 카드 셀렉터
            items = await page.query_selector_all("li.css-1mxjmrg, li[class*='ProductListItem']")

        products = []
        for item in items:
            try:
                product = await self._parse_item(item, page)
                if product:
                    products.append(product)
            except Exception as e:
                self.logger.debug(f"[kurly] 아이템 파싱 오류: {e}")

        return products

    async def _parse_item(self, item, page) -> Optional[dict]:
        name_el = await item.query_selector("[class*='name'], [class*='Title'], span[class*='css-']")
        if name_el is None:
            return None
        name_text = (await name_el.inner_text()).strip()
        if not name_text:
            return None

        # 가격 파싱 — 할인가/정가 분리
        sale_el = await item.query_selector("[class*='salePrice'], [class*='discountedPrice'], [class*='price']")
        original_el = await item.query_selector("[class*='originalPrice'], [class*='basePrice'], s")

        sale_price = _parse_price(await sale_el.inner_text() if sale_el else "")
        original_price = _parse_price(await original_el.inner_text() if original_el else "")

        if sale_price is None:
            return None

        discount_rate = 0.0
        if original_price and original_price > sale_price:
            discount_rate = round(1 - sale_price / original_price, 4)

        # 상품 URL
        link_el = await item.query_selector("a[href*='/goods/'], a[href*='/products/']")
        product_url = None
        if link_el:
            href = await link_el.get_attribute("href")
            if href:
                product_url = href if href.startswith("http") else f"https://www.kurly.com{href}"

        # 단위 — 상품명에서 추출 시도 (예: "대파 1단", "양파 1kg")
        name, unit = _split_name_unit(name_text)

        return {
            "name": name,
            "unit": unit,
            "product_url": product_url,
            "original_price": original_price,
            "discount_rate": discount_rate,
            "sale_price": sale_price,
        }


def _parse_price(text: str) -> Optional[int]:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _split_name_unit(name: str) -> tuple[str, Optional[str]]:
    """'대파 1단' → ('대파', '1단'), '양파(1kg)' → ('양파', '1kg')"""
    match = re.search(r"[\(\[]?(\d+\s*(?:kg|g|ml|L|개|단|팩|봉|box|Box))[\)\]]?", name, re.IGNORECASE)
    if match:
        unit = match.group(1).strip()
        clean = name[:match.start()].strip().rstrip("([ ")
        return clean or name, unit
    return name, None
