import re
from typing import Optional

from playwright.async_api import Page

from crawler.base import BaseCrawler


class HomeplusCrawler(BaseCrawler):
    market_key = "homeplus"
    search_url_template = "https://front.homeplus.co.kr/search?entry=direct&keyword={keyword}&sort=SALES"

    async def _fetch_products(self, page: Page, url: str) -> list[dict]:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)

        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(800)

        # 홈플러스 상품 카드 셀렉터 (우선순위 순)
        selectors = [
            "li.c-card-item",
            "ul.c-card-list > li",
            "[class*='ProductCard']",
            ".prd-list > li",
            "li[class*='product']",
        ]
        items = []
        for sel in selectors:
            items = await page.query_selector_all(sel)
            if items:
                self.logger.debug(f"[homeplus] 셀렉터 매칭: {sel} ({len(items)}개)")
                break

        if not items:
            self.logger.warning("[homeplus] 상품 리스트 셀렉터 미매칭")
            return []

        products = []
        for item in items:
            try:
                product = await self._parse_item(item)
                if product:
                    products.append(product)
            except Exception as e:
                self.logger.debug(f"[homeplus] 아이템 파싱 오류: {e}")

        return products

    async def _parse_item(self, item) -> Optional[dict]:
        name_el = await item.query_selector(
            ".c-card-item__name, .prd-name, .item-name, "
            "[class*='name'], [class*='title'], [class*='Name']"
        )
        if name_el is None:
            return None
        name_text = (await name_el.inner_text()).strip()
        if not name_text:
            return None

        sale_el = await item.query_selector(
            ".c-card-item__price-now, .sale-price, .final-price, "
            "[class*='price-now'], [class*='salePrice'], [class*='finalPrice']"
        )
        original_el = await item.query_selector(
            ".c-card-item__price-before, .origin-price, "
            "[class*='price-before'], [class*='originPrice'], del, s"
        )

        sale_price = _parse_price(await sale_el.inner_text() if sale_el else "")
        original_price = _parse_price(await original_el.inner_text() if original_el else "")

        if sale_price is None:
            return None

        discount_rate = 0.0
        discount_el = await item.query_selector(
            ".c-card-item__discount, [class*='discount'], [class*='Discount']"
        )
        if discount_el:
            rate_text = re.sub(r"[^\d]", "", await discount_el.inner_text())
            if rate_text:
                discount_rate = int(rate_text) / 100
        elif original_price and original_price > sale_price:
            discount_rate = round(1 - sale_price / original_price, 4)

        link_el = await item.query_selector("a[href*='/product/'], a[href*='/goods/'], a[href]")
        product_url = None
        if link_el:
            href = await link_el.get_attribute("href")
            if href:
                product_url = href if href.startswith("http") else f"https://front.homeplus.co.kr{href}"

        name, unit = _split_name_unit(name_text)

        image_url = await self._get_image_url(item, "https://front.homeplus.co.kr")

        return {
            "name": name,
            "unit": unit,
            "product_url": product_url,
            "image_url": image_url,
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
    match = re.search(r"[\(\[]?(\d+\s*(?:kg|g|ml|L|개|단|팩|봉|box|Box|포|통|입|장|묶음))[\)\]]?", name, re.IGNORECASE)
    if match:
        unit = match.group(1).strip()
        clean = name[:match.start()].strip().rstrip("([ ")
        return clean or name, unit
    return name, None
