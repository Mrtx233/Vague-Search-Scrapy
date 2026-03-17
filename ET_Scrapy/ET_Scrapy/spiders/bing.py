# 获取FPIG的版本
import logging
import re
from urllib.parse import quote_plus

from lxml import etree
from scrapy import Spider, Request
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

logger = logging.getLogger(__name__)


def get_proxy_config() -> dict:
    """获取代理配置，返回字典格式"""
    return {
        "server": "http://127.0.0.1:7897",
    }


class BingSpider(Spider):
    """使用 scrapy-playwright 抓取 Bing 搜索结果"""

    name = "bing"
    allowed_domains = ["www.bing.com"]

    DEFAULT_KEYWORD = ["新能源", "人工智能", "光伏", "储能"]
    MAX_PAGES = 6
    PAGING_FORM = "PORE"

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
                meta=self.build_request_meta(keyword=keyword, page_index=1),
                dont_filter=True,
            )

    def build_request_meta(self, keyword: str, page_index: int, fpig: str | None = None) -> dict:
        meta = {
            "playwright": True,
            "playwright_include_page": False,
            "playwright_page_methods": [
                PageMethod("wait_for_selector", "#b_content", timeout=30000),
            ],
            "playwright_context": "bing",
            "playwright_context_kwargs": {
                "proxy": get_proxy_config()
            },
            "page_index": page_index,
            "keyword": keyword,
        }
        if fpig:
            meta["fpig"] = fpig
        return meta

    def extract_fpig(self, response: Response) -> str | None:
        candidates = [response.url, response.text]

        for candidate in candidates:
            match = re.search(r"FPIG=([A-Z0-9]+)", candidate)
            if match:
                return match.group(1)

        return None

    def build_paged_url(self, keyword: str, fpig: str, page_index: int) -> str:
        search_query = f"{keyword} filetype:xlsx"
        encoded_query = quote_plus(search_query)
        first = (page_index - 1) * 10 + 1
        return (
            "https://www.bing.com/search?"
            f"q={encoded_query}&FPIG={fpig}&first={first}&FORM={self.PAGING_FORM}"
        )

    def parse(self, response: Response):
        """解析搜索结果页面并汇总链接"""
        if response.status != 200:
            logger.error(f"请求失败 | 状态码: {response.status}")
            return

        tree = etree.HTML(response.text)

        # 建议用这个，更稳一些
        links = tree.xpath("//li[@class='b_algo']//h2/a/@href")

        before_count = len(self.all_links)
        self.all_links.update(links)
        after_count = len(self.all_links)

        logger.info(
            f"关键词={response.meta.get('keyword')} | "
            f"当前页 page={response.meta.get('page_index')} | "
            f"提取 {len(links)} 条 | "
            f"新增 {after_count - before_count} 条 | "
            f"累计 {after_count} 条"
        )

        current_page = response.meta.get("page_index", 1)
        if current_page >= self.MAX_PAGES:
            logger.info(
                "达到最大翻页数限制，停止继续翻页 | keyword=%s | page=%s",
                response.meta.get("keyword"),
                current_page,
            )
            return

        fpig = self.extract_fpig(response) or response.meta.get("fpig")
        if not fpig:
            logger.warning(
                "未能从响应中提取 FPIG，停止继续翻页 | keyword=%s | page=%s | url=%s",
                response.meta.get("keyword"),
                current_page,
                response.url,
            )
            return

        next_page_index = current_page + 1
        next_page_url = self.build_paged_url(
            keyword=response.meta.get("keyword"),
            fpig=fpig,
            page_index=next_page_index,
        )

        logger.info(
            "继续抓取下一页 | keyword=%s | from_page=%s | next_page=%s | fpig=%s | next_url=%s",
            response.meta.get("keyword"),
            current_page,
            next_page_index,
            fpig,
            next_page_url,
        )

        yield Request(
            url=next_page_url,
            callback=self.parse,
            meta=self.build_request_meta(
                keyword=response.meta.get("keyword"),
                page_index=next_page_index,
                fpig=fpig,
            ),
            dont_filter=True,
        )

    def closed(self, reason):
        """爬虫结束时统一输出"""
        final_links = list(self.all_links)

        logger.info(f"爬虫结束，原因: {reason}")
        logger.info(f"去重后总链接数: {len(final_links)}")

        print("最终去重后的链接列表：")
        print(final_links)
