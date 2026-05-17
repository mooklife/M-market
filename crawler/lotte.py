import re
from typing import Optional

from playwright.async_api import Page

from crawler.base import BaseCrawler


class LotteCrawler(BaseCrawler):
    market_key = "lotte"
    search_url_template = "https://www.lotteon.com/p/search?q={keyword}&mall_tp=PO"

    async def _fetch_products(self, page: Page, url: str) -> list[dict]:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)

        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(800)

        items = await page.query_selector_all("li.prod_item, li[class*='prd_item']")
        if not items:
            items = await page.query_selector_all(".prod_list > li")

        products = []
        for item in items:
            try:
                product = await self._parse_item(item)
                if product:
                    products.append(product)
            except Exception as e:
                self.logger.debug(f"[lotte] 아이템 파싱 오류: {e}")

        return products

    async def _parse_item(self, item) -> Optional[dict]:
        name_el = await item.query_selector(".prd_name, .prod_name, .item_name")
        if name_el is None:
            return None
        name_text = (await name_el.inner_text()).strip()
        if not name_text:
            return None

        sale_el = await item.query_selector(".sle_prc, .sell_price, .final_price")
        original_el = await item.query_selector(".org_prc, .original_price, del, s")

        sale_price = _parse_price(await sale_el.inner_text() if sale_el else "")
        original_price = _parse_price(await original_el.inner_text() if original_el else "")

        if sale_price is None:
            return None

        discount_rate = 0.0
        discount_el = await item.query_selector(".dc_prc, .discount_rate, .sale_rate")
        if discount_el:
            rate_text = re.sub(r"[^\d]", "", await discount_el.inner_text())
            if rate_text:
                discount_rate = int(rate_text) / 100
        elif original_price and original_price > sale_price:
            discount_rate = round(1 - sale_price / original_price, 4)

        link_el = await item.query_selector("a[href*='/p/product/']")
        product_url = None
        if link_el:
            href = await link_el.get_attribute("href")
            if href:
                product_url = href if href.startswith("http") else f"https://www.lotteon.com{href}"

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
