# Playwright 直接点击“下一页”
import logging
import re
from urllib.parse import quote_plus

from lxml import etree
from scrapy import Request, Spider
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

logger = logging.getLogger(__name__)


def get_proxy_config() -> dict:
    """获取代理配置，返回字典格式"""
    return {
        "server": "http://127.0.0.1:7897",
    }


class Bing2Spider(Spider):
    """使用 Playwright 在同一页面中点击“下一页”抓取 Bing 搜索结果"""

    name = "bing2"
    allowed_domains = ["www.bing.com"]

    DEFAULT_KEYWORD = ["新能源", "人工智能", "光伏", "储能"]
    MAX_PAGES = 6
    NEXT_PAGE_SELECTORS = [
        "a.sb_pagN",
        "a[title='下一页']",
        "a[title='Next page']",
        "a[aria-label='下一页']",
        "a[aria-label='Next page']",
    ]

    def __init__(self, keyword=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if keyword:
            self.keywords = [k.strip() for k in keyword.split(",") if k.strip()]
        else:
            self.keywords = self.DEFAULT_KEYWORD

        self.all_links = set()

    def start_requests(self):
        for keyword in self.keywords:
            search_query = f"{keyword} filetype:xlsx"
            encoded_query = quote_plus(search_query)
            search_url = f"https://www.bing.com/search?q={encoded_query}"

            yield Request(
                url=search_url,
                callback=self.parse,
                meta=self.build_request_meta(keyword=keyword),
                dont_filter=True,
            )

    def build_request_meta(self, keyword: str) -> dict:
        return {
            "playwright": True,
            "playwright_include_page": True,
            "playwright_page_methods": [
                PageMethod("wait_for_selector", "#b_content", timeout=30000),
            ],
            "playwright_context": self.build_context_name(keyword),
            "playwright_context_kwargs": {
                "proxy": get_proxy_config(),
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "extra_http_headers": {
                    "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                    "sec-ch-ua-arch": '"x86"',
                    "sec-ch-ua-bitness": '"64"',
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "none",
                    "sec-fetch-user": "?1",
                }
            },
            "keyword": keyword,
        }

    def build_context_name(self, keyword: str) -> str:
        safe_keyword = re.sub(r"[^a-zA-Z0-9]+", "-", keyword).strip("-").lower()
        return f"bing2-{safe_keyword or 'default'}"

    def extract_links(self, html: str) -> list[str]:
        tree = etree.HTML(html)
        if tree is None:
            return []
        return tree.xpath("//li[@class='b_algo']//h2/a/@href")

    async def click_next_page(self, page) -> str | None:
        for selector in self.NEXT_PAGE_SELECTORS:
            locator = page.locator(selector)
            if await locator.count() == 0:
                continue

            target = locator.first
            if not await target.is_visible():
                continue

            await target.click(timeout=15000)
            return selector

        return None

    async def parse(self, response: Response):
        """在同一个 Playwright 页面中循环翻页并解析结果"""
        if response.status != 200:
            logger.error("请求失败 | 状态码: %s", response.status)
            return

        keyword = response.meta.get("keyword")
        page = response.meta["playwright_page"]

        try:
            current_page = 1
            while current_page <= self.MAX_PAGES:
                html = await page.content()
                links = self.extract_links(html)

                before_count = len(self.all_links)
                self.all_links.update(links)
                after_count = len(self.all_links)

                logger.info(
                    "关键词=%s | 当前页 page=%s | 提取 %s 条 | 新增 %s 条 | 累计 %s 条 | url=%s",
                    keyword,
                    current_page,
                    len(links),
                    after_count - before_count,
                    after_count,
                    page.url,
                )

                if current_page >= self.MAX_PAGES:
                    logger.info(
                        "达到最大翻页数限制，停止继续翻页 | keyword=%s | page=%s",
                        keyword,
                        current_page,
                    )
                    break

                previous_url = page.url
                clicked_selector = await self.click_next_page(page)
                if not clicked_selector:
                    logger.info(
                        "未找到可点击的下一页按钮，停止继续翻页 | keyword=%s | page=%s | url=%s",
                        keyword,
                        current_page,
                        previous_url,
                    )
                    break

                try:
                    await page.wait_for_function(
                        "previousUrl => window.location.href !== previousUrl",
                        arg=previous_url,
                        timeout=15000,
                    )
                except Exception:
                    logger.info(
                        "点击了下一页，但 URL 未发生变化，继续等待内容区域刷新 | keyword=%s | page=%s",
                        keyword,
                        current_page,
                    )

                await page.wait_for_selector("#b_content", timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=30000)

                logger.info(
                    "已点击下一页 | keyword=%s | from_page=%s | selector=%s | new_url=%s",
                    keyword,
                    current_page,
                    clicked_selector,
                    page.url,
                )

                current_page += 1
        finally:
            await page.close()

    def closed(self, reason):
        """爬虫结束时统一输出"""
        final_links = list(self.all_links)

        logger.info("爬虫结束，原因: %s", reason)
        logger.info("去重后总链接数: %s", len(final_links))

        print("最终去重后的链接列表：")
        print(final_links)
