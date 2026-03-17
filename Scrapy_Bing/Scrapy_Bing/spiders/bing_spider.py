import json
import logging
import os
import random
import re
import socket
import time
from urllib.parse import urlparse

import redis
import scrapy
from scrapy import Request
from scrapy.exceptions import CloseSpider
from DrissionPage import Chromium, ChromiumOptions

from Scrapy_Bing.items import BingFileItem

logger = logging.getLogger(__name__)


class BingSpider(scrapy.Spider):
    name = "bing_spider"
    allowed_domains = ["bing.com"]
    custom_settings = {
    }

    def __init__(self, keyword_path=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.keyword_path = keyword_path or r"D:\code_Python\Vague-Search-Scrapy\json\output\中文繁体\台湾交通与基础建设_A.json"
        self.request_delay = (2, 4)
        self.max_pages = 30
        self.port_range = (8200, 8300)

        self.browser = None
        self.tab = None
        self.current_keyword = None
        self.current_page = 1
        self.pending_keywords = []
        self._kw_stats = {}

        self.html_save_dir = os.path.join(os.getcwd(), "saved_html")
        self._html_dir_ready = False

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.rds = redis.Redis(
            host=crawler.settings["REDIS_HOST"],
            port=crawler.settings.getint("REDIS_PORT"),
            db=crawler.settings.getint("REDIS_DB"),
            decode_responses=True,
        )
        spider.redis_prefix = crawler.settings["REDIS_PREFIX"]
        spider.max_pages = crawler.settings.getint("MAX_PAGES", spider.max_pages)
        rd = crawler.settings.get("REQUEST_DELAY")
        if isinstance(rd, (list, tuple)) and len(rd) == 2:
            spider.request_delay = tuple(rd)
        spider.port_range = crawler.settings.get("PORT_RANGE", spider.port_range)
        spider.user_agent = crawler.settings.get("USER_AGENT")
        return spider

    def start_requests(self):
        self.pending_keywords = self.load_keywords(self.keyword_path)
        self.pending_keywords = [kw for kw in self.pending_keywords if not self.is_finished_bing(kw)]
        if not self.pending_keywords:
            self.logger.info("无待处理关键词")
            return

        first_kw = self.pending_keywords.pop(0)
        self.current_keyword = first_kw
        yield Request(
            url="https://www.bing.com",
            callback=self.search_keyword,
            meta={"keyword": first_kw},
            dont_filter=True,
        )

    def is_finished_bing(self, keyword):
        return self.rds.sismember(f"{self.redis_prefix}:keyword_finished:bing", keyword)

    def mark_finished_bing(self, keyword):
        self.rds.sadd(f"{self.redis_prefix}:keyword_finished:bing", keyword)
        s = self._kw_stats.get(keyword, {})
        pages = s.get("pages", 0)
        items = s.get("items", 0)
        self.logger.info(f"关键词已处理完成并标记: {keyword} | pages={pages} | items={items}")

    def _next_keyword_request(self):
        while self.pending_keywords:
            kw = self.pending_keywords.pop(0)
            if self.is_finished_bing(kw):
                self.logger.info(f"跳过已完成关键词: {kw}")
                continue
            self.current_keyword = kw
            self.current_page = 1
            return Request(
                url="https://www.bing.com",
                callback=self.search_keyword,
                meta={"keyword": kw},
                dont_filter=True,
            )
        return None

    def _get_available_port(self):
        start, end = self.port_range
        ports = list(range(start, end + 1))
        random.shuffle(ports)
        for port in ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("localhost", port))
                    return port
            except OSError:
                continue
        return random.randint(start, end)

    def get_proxy(self):
        """获取代理配置"""
        proxyHost = "u10097.20.tp.16yun.cn"
        proxyPort = "6447"
        proxyUser = "16XUBUTY"
        proxyPass = "656882"
        proxyMeta = f"http://{proxyUser}:{proxyPass}@{proxyHost}:{proxyPort}"
        proxies = {
            "HTTP": proxyMeta,
            "HTTPS": proxyMeta,
        }
        tunnel = random.randint(1, 10000)
        headers = {"Proxy-Tunnel": str(tunnel)}
        return proxies

    def _init_browser(self):
        try:
            co = ChromiumOptions()
            co.set_local_port(self._get_available_port())
            co.set_argument("--disable-blink-features=AutomationControlled")
            co.set_argument("--disable-gpu")
            co.set_argument("--no-first-run")
            co.set_argument("--disable-translate")
            co.set_argument("--no-sandbox")
            co.set_argument("--disable-dev-shm-usage")
            
            # Use the proxy from get_proxy()
            proxies = self.get_proxy()
            # DrissionPage uses 'http://user:pass@host:port' format
            self.proxy_url = proxies["HTTPS"] 
            co.set_argument(f"--proxy-server={self.proxy_url}")
            
            if self.user_agent:
                co.set_user_agent(self.user_agent)
            self.browser = Chromium(co)
            self.tab = self.browser.new_tab()
            self.logger.info(f"浏览器初始化完成，使用代理 {self.proxy_url}")
        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            raise CloseSpider("browser_init_failed")

    def _ensure_browser(self):
        if self.browser is None or self.tab is None:
            self._init_browser()

    def _sanitize_filename(self, name):
        safe = re.sub(r"[^\w.-]", "_", name)
        return safe or "unknown"

    def _ensure_html_dir(self):
        if not self._html_dir_ready:
            os.makedirs(self.html_save_dir, exist_ok=True)
            self._html_dir_ready = True

    def _save_page_html(self, keyword, page_no, html_text):
        self._ensure_html_dir()
        file_name = f"{self._sanitize_filename(str(keyword))}_p{page_no}.html"
        file_path = os.path.join(self.html_save_dir, file_name)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_text)
            self.logger.info(f"已保存页面 HTML: {file_path}")
        except Exception as e:
            self.logger.error(f"保存页面 HTML 失败: {e}")

    def _next_page(self):
        try:
            next_buttons = self.tab.eles(
                'xpath://a[@title="下一页"] | //a[@aria-label="下一页"] | //a[@title="Next page"] | //a[@aria-label="Next page"]'
            )
            if next_buttons:
                next_buttons[-1].click()
                self.tab.wait.load_start(timeout=15)
                time.sleep(random.uniform(*self.request_delay))
                return True
            return False
        except Exception as e:
            self.logger.warning(f"翻页失败: {e}")
            return False

    def _crawl_keyword(self, keyword):
        self._kw_stats.setdefault(keyword, {"pages": 0, "items": 0})
        self.current_page = 1

        self.tab.get("https://www.bing.com")
        self.tab.wait.load_start()
        time.sleep(random.uniform(*self.request_delay))

        # Check if we are on a search page or home page
        search_box = self.tab.ele('xpath://input[@name="q"] | //textarea[@name="q"] | //input[@id="sb_form_q"]', timeout=5)
        if not search_box:
             self.logger.warning(f"无法找到搜索框，当前URL: {self.tab.url}")
             return

        search_query = f'"{keyword}" filetype:xlsx'
        search_box.input(search_query, clear=True)
        
        # Click search button or press enter
        search_btn = self.tab.ele('xpath://label[@id="search_icon"] | //input[@id="sb_form_go"] | //label[@for="sb_form_go"]', timeout=2)
        if search_btn:
            search_btn.click()
        else:
             search_box.input("\n")
             
        self.tab.wait.load_start()
        time.sleep(random.uniform(*self.request_delay))

        while self.current_page <= self.max_pages:
            # Check for captcha or no results
            if "因为包含了通常与垃圾邮件相关的字词" in self.tab.html or "There are no results for" in self.tab.html:
                 self.logger.warning(f"关键词[{keyword}] 无结果或被拦截")
                 break

            try:
                # Wait for results to appear
                self.tab.wait.ele_displayed('xpath://li[@class="b_algo"]', timeout=10)
            except Exception:
                self.logger.warning(f"关键词[{keyword}] 第{self.current_page}页无搜索结果元素，结束")
                break

            self._kw_stats[keyword]["pages"] = max(self._kw_stats[keyword]["pages"], self.current_page)
            self.logger.info(f"解析关键词 {keyword} | page={self.current_page}")
            # self._save_page_html(keyword, self.current_page, self.tab.html) # Disable saving html to save space

            results = self.tab.eles('xpath://li[@class="b_algo"]') # Get the li elements first
            if not results:
                self.logger.warning(f"关键词[{keyword}] 第{self.current_page}页无结果列表")
                break

            extracted = 0
            for res in results:
                try:
                    # Extract from within the li element
                    title_ele = res.ele('.//h2/a')
                    if not title_ele:
                         continue
                         
                    url = title_ele.attr("href")
                    title_parts = title_ele.text
                    title = title_parts.strip() if title_parts else ""

                    if not url:
                        continue
                    
                    # Print for debugging
                    print(f"[{keyword}] Found: {title} -> {url}")

                    item = BingFileItem()
                    item["url"] = url
                    item["title"] = title
                    # item["file_type"] = "xlsx" # Let pipeline handle or guess
                    item["keyword"] = keyword
                    try:
                        item["website"] = urlparse(url).netloc
                    except:
                        item["website"] = "unknown"
                        
                    extracted += 1
                    yield item
                except Exception as e:
                    self.logger.warning(f"解析单个结果失败: {e}")
                    continue

            self._kw_stats[keyword]["items"] += extracted
            self.logger.info(f"完成页面: {keyword} | page={self.current_page} | extracted={extracted}")

            if not self._next_page():
                self.logger.info(f"关键词[{keyword}] 无下一页，结束")
                break

            self.current_page += 1


    def search_keyword(self, response):
        keyword = response.meta["keyword"]
        self._ensure_browser()
        try:
            yield from self._crawl_keyword(keyword)
        except Exception as e:
            self.logger.error(f"处理关键词[{keyword}]失败: {e}")
        finally:
            self.mark_finished_bing(keyword)
            next_req = self._next_keyword_request()
            if next_req:
                yield next_req

    def load_keywords(self, path):
        try:
            if not os.path.exists(path):
                self.logger.error(f"关键词文件不存在: {path}")
                return []
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                return [item["外文"] for item in data if item.get("外文")]
        except Exception as e:
            self.logger.error(f"加载关键词异常: {e}")
            return []

    def closed(self, reason):
        self.logger.info(f"爬虫关闭，原因: {reason}")
        try:
            if self.tab:
                self.tab.close()
            if self.browser:
                self.browser.quit()
            self.logger.info("浏览器已关闭")
        except Exception as e:
            self.logger.error(f"关闭浏览器失败: {e}")
