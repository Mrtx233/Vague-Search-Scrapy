import logging
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

    def __init__(self, keyword=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if keyword:
            self.keywords = [k.strip() for k in keyword.split(",") if k.strip()]
        else:
            self.keywords = self.DEFAULT_KEYWORD

        self.all_links = set()  # 用于去重汇总

    def start_requests(self):
        for keyword in self.keywords:
            search_query = f"{keyword} filetype:xlsx"
            encoded_query = quote_plus(search_query)

            for first in range(1, 52, 10):  # 1, 11, 21, ..., 101
                search_url = (
                    f"https://www.bing.com/search?"
                    f"q={encoded_query}&first={first}&FORM=PORE"
                )

                yield Request(
                    url=search_url,
                    callback=self.parse,
                    meta={
                        "playwright": True,
                        "playwright_include_page": False,
                        "playwright_page_methods": [
                            PageMethod("wait_for_selector", "#b_content", timeout=30000),
                        ],
                        "playwright_context_kwargs": {
                            "proxy": get_proxy_config()
                        },
                        "first": first,
                        "keyword": keyword,
                    },
                    dont_filter=True,
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
            f"当前页 first={response.meta.get('first')} | "
            f"提取 {len(links)} 条 | "
            f"新增 {after_count - before_count} 条 | "
            f"累计 {after_count} 条"
        )

    def closed(self, reason):
        """爬虫结束时统一输出"""
        final_links = list(self.all_links)

        logger.info(f"爬虫结束，原因: {reason}")
        logger.info(f"去重后总链接数: {len(final_links)}")

        print("最终去重后的链接列表：")
        print(final_links)