import re
from typing import Optional

from playwright.async_api import Page

from crawler.base import BaseCrawler


class OasisCrawler(BaseCrawler):
    market_key = "oasis"
    # rows=60 으로 한 번에 최대 60개 수집
    search_url_template = (
        "https://www.oasis.co.kr/product/search"
        "?keyword={keyword}&page=1&sort=priority&direction=desc&rows=60"
    )

    async def _fetch_products(self, page: Page, url: str) -> list[dict]:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # 상품 리스트가 렌더링될 때까지 대기
        try:
            await page.wait_for_selector("li.prd_item, ul.prd_list li, .product_list li", timeout=10000)
        except Exception:
            await page.wait_for_timeout(3000)

        # 셀렉터 우선순위 순으로 시도
        selectors = [
            "li.prd_item",
            "ul.prd_list > li",
            ".product_list > ul > li",
            "ul[class*='prd'] > li",
            "ul[class*='product'] > li",
        ]
        items = []
        for sel in selectors:
            items = await page.query_selector_all(sel)
            if items:
                self.logger.debug(f"[oasis] 셀렉터 매칭: {sel} ({len(items)}개)")
                break

        if not items:
            self.logger.warning("[oasis] 상품 리스트 셀렉터 미매칭 — 텍스트 파싱으로 전환")
            return await self._parse_from_text(page)

        products = []
        for item in items:
            try:
                product = await self._parse_item(item)
                if product:
                    products.append(product)
            except Exception as e:
                self.logger.debug(f"[oasis] 아이템 파싱 오류: {e}")

        return products

    async def _parse_item(self, item) -> Optional[dict]:
        # 상품명
        name_el = await item.query_selector(
            ".prd_name, .name, .product_name, .goods_name, "
            "[class*='name'], [class*='title']"
        )
        if name_el is None:
            return None
        name_text = (await name_el.inner_text()).strip()
        if not name_text:
            return None

        # 판매가 (할인 적용가)
        sale_el = await item.query_selector(
            ".dc_price, .sale_price, .sell_price, .final_price, "
            "[class*='dc_price'], [class*='sale'], strong.price"
        )
        # 정가
        original_el = await item.query_selector(
            ".org_price, .original_price, .consumer_price, "
            "[class*='org_price'], [class*='origin'], del, s"
        )

        sale_price = _parse_price(await sale_el.inner_text() if sale_el else "")
        original_price = _parse_price(await original_el.inner_text() if original_el else "")

        if sale_price is None:
            # 가격 텍스트 전체에서 파싱 시도
            all_text = await item.inner_text()
            prices = _extract_all_prices(all_text)
            if not prices:
                return None
            sale_price = min(prices)
            original_price = max(prices) if len(prices) > 1 else None

        discount_rate = 0.0
        dc_el = await item.query_selector(
            ".dc_percent, .discount_rate, .dc_rate, [class*='dc_percent'], [class*='percent']"
        )
        if dc_el:
            rate_text = re.sub(r"[^\d]", "", await dc_el.inner_text())
            if rate_text:
                discount_rate = int(rate_text) / 100
        elif original_price and original_price > sale_price:
            discount_rate = round(1 - sale_price / original_price, 4)

        link_el = await item.query_selector("a[href*='/product/detail'], a[href*='/goods/']")
        if link_el is None:
            link_el = await item.query_selector("a[href]")
        product_url = None
        if link_el:
            href = await link_el.get_attribute("href")
            if href:
                product_url = href if href.startswith("http") else f"https://www.oasis.co.kr{href}"

        name, unit = _split_name_unit(name_text)

        return {
            "name": name,
            "unit": unit,
            "product_url": product_url,
            "original_price": original_price,
            "discount_rate": discount_rate,
            "sale_price": sale_price,
        }

    async def _parse_from_text(self, page: Page) -> list[dict]:
        """JS 렌더링 실패 시 페이지 텍스트에서 직접 파싱"""
        text = await page.inner_text("body")
        products = []
        # 패턴: "상품명\n...XX% N,NNN원 N,NNN원"
        pattern = re.compile(
            r"([가-힣a-zA-Z0-9\[\]()/ .~*&,%-]+)\s*\n"  # 상품명
            r".*?(\d+)%\s*\*?\*?(\d[\d,]+)\*?\*?원\s*\*?\*?(\d[\d,]+)\*?\*?원",
            re.DOTALL,
        )
        for m in pattern.finditer(text):
            name_raw, rate_str, sale_str, orig_str = m.groups()
            name_raw = name_raw.strip()
            if len(name_raw) < 2 or len(name_raw) > 80:
                continue
            sale_price = int(sale_str.replace(",", ""))
            original_price = int(orig_str.replace(",", ""))
            discount_rate = int(rate_str) / 100 if rate_str != "0" else 0.0
            name, unit = _split_name_unit(name_raw)
            products.append({
                "name": name,
                "unit": unit,
                "product_url": None,
                "original_price": original_price,
                "discount_rate": discount_rate,
                "sale_price": sale_price,
            })
            if len(products) >= 60:
                break

        self.logger.info(f"[oasis] 텍스트 파싱으로 {len(products)}건 추출")
        return products


def _parse_price(text: str) -> Optional[int]:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _extract_all_prices(text: str) -> list[int]:
    """텍스트에서 '원' 앞의 숫자들을 모두 추출"""
    matches = re.findall(r"([\d,]+)원", text)
    result = []
    for m in matches:
        v = int(m.replace(",", ""))
        if 100 <= v <= 10_000_000:
            result.append(v)
    return result


def _split_name_unit(name: str) -> tuple[str, Optional[str]]:
    match = re.search(
        r"[\(\[]?(\d+\s*(?:kg|g|ml|L|개|단|팩|봉|box|Box|포|통|입|장|묶음))[\)\]]?",
        name, re.IGNORECASE
    )
    if match:
        unit = match.group(1).strip()
        clean = name[:match.start()].strip().rstrip("([ ")
        return (clean or name), unit
    return name, None
