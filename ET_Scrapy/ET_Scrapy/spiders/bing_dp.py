# Drissionpage
import logging
import random
import socket
import time

import scrapy
from DrissionPage import Chromium, ChromiumOptions
from scrapy import Request
from scrapy.exceptions import CloseSpider

logger = logging.getLogger(__name__)


def get_proxy_config() -> dict:
    """获取代理配置，返回字典格式"""
    return {
        "server": "http://127.0.0.1:7897",
    }


class BingDpSpider(scrapy.Spider):
    """使用 DrissionPage 在同一浏览器页面中点击“下一页”抓取 Bing 搜索结果"""

    name = "bing_dp"
    allowed_domains = ["www.bing.com"]

    DEFAULT_KEYWORD = ["新能源", "人工智能", "光伏", "储能"]
    MAX_PAGES = 6
    REQUEST_DELAY = (2, 4)
    PORT_RANGE = (8200, 8300)
    NEXT_PAGE_XPATH = (
        'xpath://a[@title="下一页"]'
        ' | //a[@aria-label="下一页"]'
        ' | //a[@title="Next page"]'
        ' | //a[@aria-label="Next page"]'
        ' | //a[contains(@class, "sb_pagN")]'
    )

    def __init__(self, keyword=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if keyword:
            self.keywords = [k.strip() for k in keyword.split(",") if k.strip()]
        else:
            self.keywords = self.DEFAULT_KEYWORD

        self.browser = None
        self.tab = None
        self.all_links = set()

    def start_requests(self):
        yield Request(
            url="https://www.bing.com",
            callback=self.parse,
            dont_filter=True,
        )

    def _get_available_port(self) -> int:
        start, end = self.PORT_RANGE
        ports = list(range(start, end + 1))
        random.shuffle(ports)
        for port in ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(("127.0.0.1", port))
                    return port
            except OSError:
                continue
        return random.randint(start, end)

    def _init_browser(self):
        try:
            proxy_url = get_proxy_config()["server"]

            co = ChromiumOptions()
            co.set_local_port(self._get_available_port())
            co.set_argument("--disable-blink-features=AutomationControlled")
            co.set_argument("--disable-gpu")
            co.set_argument("--no-first-run")
            co.set_argument("--disable-translate")
            co.set_argument("--no-sandbox")
            co.set_argument("--disable-dev-shm-usage")
            co.set_argument("--start-maximized")
            co.set_argument(f"--proxy-server={proxy_url}")

            self.browser = Chromium(co)
            self.tab = self.browser.new_tab()
            logger.info("DrissionPage 浏览器初始化完成 | proxy=%s", proxy_url)
        except Exception as exc:
            logger.error("DrissionPage 浏览器初始化失败: %s", exc)
            raise CloseSpider("browser_init_failed") from exc

    def _ensure_browser(self):
        if self.browser is None or self.tab is None:
            self._init_browser()

    def _sleep(self):
        time.sleep(random.uniform(*self.REQUEST_DELAY))

    def _extract_links(self) -> list[str]:
        try:
            return self.tab.eles('xpath://li[@class="b_algo"]//h2/a/@href')
        except Exception as exc:
            logger.warning("提取结果链接失败: %s", exc)
            return []

    def _click_next_page(self) -> bool:
        try:
            next_buttons = self.tab.eles(self.NEXT_PAGE_XPATH)
            if not next_buttons:
                return False

            next_buttons[-1].scroll.to_see()
            next_buttons[-1].click()
            self.tab.wait.load_start(timeout=15)
            self._sleep()
            return True
        except Exception as exc:
            logger.warning("点击下一页失败: %s", exc)
            return False

    def _is_blocked_page(self) -> bool:
        html = self.tab.html or ""
        blocked_markers = [
            "请输入验证码",
            "unusual traffic",
            "verify you are human",
            "为了继续搜索，请完成下列验证码",
        ]
        return any(marker.lower() in html.lower() for marker in blocked_markers)

    def _search_keyword(self, keyword: str):
        search_query = f"{keyword} filetype:xlsx"

        self.tab.get("https://www.bing.com", timeout=30)
        self.tab.wait.load_start(timeout=20)
        self._sleep()

        search_box = self.tab.ele(
            'xpath://input[@name="q"] | //textarea[@name="q"] | //input[@id="sb_form_q"]',
            timeout=10,
        )
        if not search_box:
            logger.warning("无法找到搜索框 | keyword=%s | url=%s", keyword, self.tab.url)
            return

        search_box.input(search_query, clear=True)

        search_button = self.tab.ele(
            'xpath://label[@id="search_icon"] | //input[@id="sb_form_go"] | //label[@for="sb_form_go"]',
            timeout=2,
        )
        if search_button:
            search_button.click()
        else:
            search_box.input("\n")

        self.tab.wait.load_start(timeout=20)
        self._sleep()

        current_page = 1
        while current_page <= self.MAX_PAGES:
            if self._is_blocked_page():
                logger.warning("检测到风控/验证码页面，停止翻页 | keyword=%s | url=%s", keyword, self.tab.url)
                break

            try:
                self.tab.wait.ele_displayed('xpath://li[@class="b_algo"]', timeout=10)
            except Exception:
                logger.warning(
                    "当前页未出现搜索结果，停止翻页 | keyword=%s | page=%s | url=%s",
                    keyword,
                    current_page,
                    self.tab.url,
                )
                break

            links = self._extract_links()
            before_count = len(self.all_links)
            self.all_links.update(link for link in links if link)
            after_count = len(self.all_links)

            logger.info(
                "关键词=%s | 当前页 page=%s | 提取 %s 条 | 新增 %s 条 | 累计 %s 条 | url=%s",
                keyword,
                current_page,
                len(links),
                after_count - before_count,
                after_count,
                self.tab.url,
            )

            if current_page >= self.MAX_PAGES:
                logger.info("达到最大翻页数限制，停止继续翻页 | keyword=%s | page=%s", keyword, current_page)
                break

            if not self._click_next_page():
                logger.info("未找到可点击的下一页按钮，停止继续翻页 | keyword=%s | page=%s | url=%s", keyword, current_page, self.tab.url)
                break

            current_page += 1

    def parse(self, response):
        self._ensure_browser()

        try:
            for keyword in self.keywords:
                logger.info("开始处理关键词: %s", keyword)
                self._search_keyword(keyword)
        finally:
            self._close_browser()

    def _close_browser(self):
        if self.tab is not None:
            try:
                self.tab.close()
            except Exception:
                pass
            self.tab = None

        if self.browser is not None:
            try:
                self.browser.quit()
            except Exception:
                pass
            self.browser = None

    def closed(self, reason):
        self._close_browser()

        final_links = list(self.all_links)
        logger.info("爬虫结束，原因: %s", reason)
        logger.info("去重后总链接数: %s", len(final_links))

        print("最终去重后的链接列表：")
        print(final_links)
