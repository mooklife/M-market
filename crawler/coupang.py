import re
from typing import Optional

from playwright.async_api import Page

from crawler.base import BaseCrawler


class CoupangCrawler(BaseCrawler):
    market_key = "coupang"
    category_url = {
        "vegetable": "https://www.coupang.com/np/categories/449952",  # 채소
        "fruit":     "https://www.coupang.com/np/categories/449951",  # 과일
        "grocery":   "https://www.coupang.com/np/categories/449939",  # 가공식품
    }

    async def _fetch_products(self, page: Page, url: str) -> list[dict]:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)

        # 스크롤로 추가 상품 로드
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(800)

        items = await page.query_selector_all("li.baby-product, li[id^='productId']")
        if not items:
            items = await page.query_selector_all("ul.baby-product-list > li")

        products = []
        for item in items:
            try:
                product = await self._parse_item(item)
                if product:
                    products.append(product)
            except Exception as e:
                self.logger.debug(f"[coupang] 아이템 파싱 오류: {e}")

        return products

    async def _parse_item(self, item) -> Optional[dict]:
        name_el = await item.query_selector(".name, .product-name, .baby-product-name")
        if name_el is None:
            return None
        name_text = (await name_el.inner_text()).strip()
        if not name_text:
            return None

        sale_el = await item.query_selector(".price-value, .sale-price, strong.price-value")
        original_el = await item.query_selector(".base-price, .original-price, del")

        sale_price = _parse_price(await sale_el.inner_text() if sale_el else "")
        original_price = _parse_price(await original_el.inner_text() if original_el else "")

        if sale_price is None:
            return None

        discount_rate = 0.0
        discount_el = await item.query_selector(".discount-rate, .percent-value")
        if discount_el:
            rate_text = re.sub(r"[^\d]", "", await discount_el.inner_text())
            if rate_text:
                discount_rate = int(rate_text) / 100
        elif original_price and original_price > sale_price:
            discount_rate = round(1 - sale_price / original_price, 4)

        link_el = await item.query_selector("a[href*='/vp/products/'], a.baby-product-link")
        product_url = None
        if link_el:
            href = await link_el.get_attribute("href")
            if href:
                product_url = href if href.startswith("http") else f"https://www.coupang.com{href}"

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
    match = re.search(r"[\(\[]?(\d+\s*(?:kg|g|ml|L|개|단|팩|봉|box|Box))[\)\]]?", name, re.IGNORECASE)
    if match:
        unit = match.group(1).strip()
        clean = name[:match.start()].strip().rstrip("([ ")
        return clean or name, unit
    return name, None
