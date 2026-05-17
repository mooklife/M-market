import re
from typing import Optional

from playwright.async_api import Page

from crawler.base import BaseCrawler


class LotteCrawler(BaseCrawler):
    market_key = "lotte"
    search_url_template = "https://lottemartzetta.com/products/search?q={keyword}"

    async def _fetch_products(self, page: Page, url: str) -> list[dict]:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)

        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(800)

        # 롯데마트 제타몰 상품 카드 셀렉터 (우선순위 순)
        selectors = [
            "product-card",
            "li[class*='grid__item']",
            ".card-wrapper",
            "li.product-item",
            "[class*='product-card']",
        ]
        items = []
        for sel in selectors:
            items = await page.query_selector_all(sel)
            if items:
                self.logger.debug(f"[lotte] 셀렉터 매칭: {sel} ({len(items)}개)")
                break

        if not items:
            self.logger.warning("[lotte] 상품 카드 셀렉터 미매칭")
            return []

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
        # 상품명: h3 태그 우선
        name_el = await item.query_selector(
            "h3, h2, [class*='title'], [class*='name'], [class*='Name']"
        )
        if name_el is None:
            return None
        name_text = (await name_el.inner_text()).strip()
        if not name_text:
            return None

        # 가격: "가격X,XXX원" 형태 또는 일반 가격 셀렉터
        sale_el = await item.query_selector(
            "[class*='price']:not([class*='compare']):not([class*='original']), "
            "[class*='Price']:not([class*='Compare'])"
        )
        original_el = await item.query_selector(
            "[class*='compare-price'], [class*='original-price'], s, del"
        )

        sale_raw = await sale_el.inner_text() if sale_el else ""
        original_raw = await original_el.inner_text() if original_el else ""

        # "가격1,990원" 형태 대응
        sale_price = _parse_price(sale_raw)
        original_price = _parse_price(original_raw)

        if sale_price is None:
            # 카드 전체 텍스트에서 "가격X원" 패턴 파싱
            all_text = await item.inner_text()
            m = re.search(r"가격\s*([\d,]+)원", all_text)
            if m:
                sale_price = int(m.group(1).replace(",", ""))
            if sale_price is None:
                return None

        discount_rate = 0.0
        if original_price and original_price > sale_price:
            discount_rate = round(1 - sale_price / original_price, 4)

        # 상품 링크
        link_el = await item.query_selector("a[href*='/products/']")
        product_url = None
        if link_el:
            href = await link_el.get_attribute("href")
            if href:
                product_url = href if href.startswith("http") else f"https://lottemartzetta.com{href}"

        name, unit = _split_name_unit(name_text)

        image_url = await self._get_image_url(item, "https://lottemartzetta.com")

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
    match = re.search(
        r"[\(\[]?(\d+\s*(?:kg|g|ml|L|개|단|팩|봉|box|Box|포|통|입|장|묶음))[\)\]]?",
        name, re.IGNORECASE
    )
    if match:
        unit = match.group(1).strip()
        clean = name[:match.start()].strip().rstrip("([ ")
        return clean or name, unit
    return name, None
