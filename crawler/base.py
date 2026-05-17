import os
from abc import ABC, abstractmethod
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from utils.logger import setup_custom_logger


class BaseCrawler(ABC):
    """모든 마켓 크롤러의 추상 기본 클래스.

    하위 클래스 구현 의무:
        - market_key: str — crawler_key와 동일 (예: 'kurly')
        - search_url_template: str — '{keyword}' 플레이스홀더 포함 검색 URL
          예: 'https://www.kurly.com/search?sword={keyword}'
        - _fetch_products(page, url) → list[dict]
    """

    market_key: str = ""
    search_url_template: str = ""  # '{keyword}' 플레이스홀더 필수

    def __init__(self) -> None:
        self.logger = setup_custom_logger(f"Crawler.{self.market_key}", log_prefix="crawler")
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def crawl(self, category_key: str, keyword: str) -> list[dict]:
        """크롤링 실행 후 상품 목록 반환.

        Args:
            category_key: 카테고리 키 (예: 'vegetable')
            keyword: 검색어 (예: '야채') — categories.search_keyword 에서 전달됨
        Returns:
            list of dict with keys:
                name, unit, product_url, original_price, discount_rate, sale_price
        """
        if not self.search_url_template:
            self.logger.warning(f"[{self.market_key}] search_url_template 미설정 — 건너뜀")
            return []

        url = self.search_url_template.format(keyword=keyword)
        self.logger.info(f"[{self.market_key}] '{keyword}' 검색 크롤링 시작: {url}")
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
            if self._requires_login():
                await self._login(context)
            page = await context.new_page()
            try:
                products = await self._fetch_products(page, url)
            finally:
                await browser.close()

        self.logger.info(f"[{self.market_key}] '{keyword}' 수집 완료 — {len(products)}건")
        return products

    @abstractmethod
    async def _fetch_products(self, page: Page, url: str) -> list[dict]:
        """페이지를 파싱해 상품 목록을 반환한다.

        반환 형식 (PROJECT.md 섹션 5-2):
            {
                "name": str,
                "unit": str | None,
                "product_url": str | None,
                "original_price": int | None,
                "discount_rate": float,   # 0.0 ~ 1.0
                "sale_price": int,
            }
        """

    @staticmethod
    async def _get_image_url(item, base_url: str = "") -> Optional[str]:
        """상품 카드에서 썸네일 이미지 URL 추출. lazy-load 속성도 확인."""
        img_el = await item.query_selector("img")
        if img_el is None:
            return None
        src = await img_el.get_attribute("src")
        if not src or src.startswith("data:") or "placeholder" in (src or "").lower():
            src = (
                await img_el.get_attribute("data-src")
                or await img_el.get_attribute("data-lazy-src")
                or await img_el.get_attribute("data-original")
            )
        if not src or src.startswith("data:"):
            return None
        if src.startswith("//"):
            return "https:" + src
        if src.startswith("/"):
            return base_url.rstrip("/") + src
        return src

    def _requires_login(self) -> bool:
        login_id = os.getenv(f"{self.market_key.upper()}_ID")
        return login_id is not None and login_id != ""

    async def _login(self, context: BrowserContext) -> None:
        """로그인이 필요한 마켓에서 오버라이드한다."""
        self.logger.info(f"[{self.market_key}] 로그인 처리 — 하위 클래스에서 구현 필요")
