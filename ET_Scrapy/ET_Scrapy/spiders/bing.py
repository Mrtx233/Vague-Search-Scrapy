import os
import logging
from pathlib import Path
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from lxml import etree
from scrapy import Spider, Request
from scrapy.http import Response

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

    # 默认关键词和输出文件名
    DEFAULT_KEYWORD = "新能源"

    def __init__(self, keyword=None, output_file=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 接收命令行参数
        self.keyword = keyword if keyword else self.DEFAULT_KEYWORD

    def start_requests(self):
        """构建并发送初始请求"""
        # 构建搜索 URL：关键词 + filetype:pptx
        search_query = f"{self.keyword} filetype:pptx"
        search_url = f"https://www.bing.com/search?q=%E6%96%B0%E8%83%BD%E6%BA%90+filetype%3axlsx"

        yield Request(
            url=search_url,
            callback=self.parse,
            meta={
                "playwright": True,  # 启用 Playwright
                "playwright_include_page": False,  # 不需要获取 page 对象，只需响应
                "playwright_page_methods": [
                    {
                        "method": "wait_for_selector",
                        "args": ["#b_content", {"timeout": 30000}]  # 等待搜索结果区域加载
                    }
                ],
                "playwright_context_kwargs": {
                    "proxy": get_proxy_config()  # 设置代理
                },
            },
            dont_filter=True,
        )

    def parse(self, response: Response):
        """解析搜索结果页面并提取链接"""

        # 检查响应状态
        if response.status != 200:
            logger.error(f"请求失败 | 状态码: {response.status}")
            return

        # 使用 lxml 解析 HTML
        html_content = response.text
        tree = etree.HTML(html_content)

        # 使用 XPath 提取搜索结果链接
        links = tree.xpath("//div[@class='b_title']/h2/a/@href")

        link_list = [link for link in links]
        print(link_list)