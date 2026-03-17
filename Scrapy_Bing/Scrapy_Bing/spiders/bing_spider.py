import scrapy
import json
import os
import redis
from urllib.parse import quote
from Scrapy_Bing.items import BingFileItem
import re

class BingSpider(scrapy.Spider):
    name = 'bing_spider'
    allowed_domains = ['bing.com']

    def __init__(self, keyword_path=None, *args, **kwargs):
        super(BingSpider, self).__init__(*args, **kwargs)
        self.keyword_path = keyword_path or r"D:\code_Python\Vague-Search-Scrapy\json\output\中文繁体\台湾交通与基础建设_A.json"
        self._kw_stats = {}
        self._keyword_iter = None
        self.proxy_url = "http://127.0.0.1:7897"
        self.html_save_dir = os.path.join(os.getcwd(), "saved_html")
        self._html_dir_ready = False

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.rds = redis.Redis(
            host=crawler.settings['REDIS_HOST'],
            port=crawler.settings.getint('REDIS_PORT'),
            db=crawler.settings.getint('REDIS_DB'),
            decode_responses=True
        )
        spider.redis_prefix = crawler.settings['REDIS_PREFIX']
        return spider

    def is_finished_bing(self, keyword):
        return self.rds.sismember(f"{self.redis_prefix}:keyword_finished:bing", keyword)

    def mark_finished_bing(self, keyword):
        self.rds.sadd(f"{self.redis_prefix}:keyword_finished:bing", keyword)
        s = self._kw_stats.get(keyword, {})
        pages = s.get("pages", 0)
        items = s.get("items", 0)
        self.logger.info(f"关键词已处理完成并标记: {keyword} | pages={pages} | items={items}")

    def _build_keyword_request(self, kw):
        search_query = f'"{kw}" filetype:xlsx'
        url = f"https://www.bing.com/search?q={quote(search_query)}"
        self._kw_stats.setdefault(kw, {"pages": 0, "items": 0})
        self.logger.info(f"开始关键词: {kw} | page=1")

        return scrapy.Request(
            url,
            callback=self.parse,
            meta={
                'keyword': kw,
                'playwright': True,
                'playwright_context': 'default',
                'page_no': 1,
                'playwright_page_goto_kwargs': {
                    'wait_until': 'networkidle',
                    'timeout': 60000,
                },
                'proxy': self.proxy_url
            }
        )

    def _next_unfinished_keyword_request(self):
        if self._keyword_iter is None:
            return None
        while True:
            try:
                kw = next(self._keyword_iter)
            except StopIteration:
                return None
            if self.is_finished_bing(kw):
                self.logger.info(f"跳过已完成关键词: {kw}")
                continue
            return self._build_keyword_request(kw)

    def start_requests(self):
        keywords = self.load_keywords(self.keyword_path)
        self._keyword_iter = iter(keywords)
        first_req = self._next_unfinished_keyword_request()
        if first_req:
            yield first_req

    def _sanitize_filename(self, name):
        """Keep filename safe for Windows; replace unsupported chars with underscore."""
        safe = re.sub(r"[^\w.-]", "_", name)
        return safe or "unknown"

    def _ensure_html_dir(self):
        if not self._html_dir_ready:
            os.makedirs(self.html_save_dir, exist_ok=True)
            self._html_dir_ready = True

    def _save_response_html(self, response):
        """Persist HTML for debugging XPath issues."""
        self._ensure_html_dir()
        keyword = response.meta.get("keyword", "unknown")
        page_no = response.meta.get("page_no", 1)
        file_name = f"{self._sanitize_filename(str(keyword))}_p{page_no}.html"
        file_path = os.path.join(self.html_save_dir, file_name)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(response.text)
            self.logger.info(f"Saved HTML to {file_path}")
        except Exception as e:
            self.logger.error(f"Save HTML failed: {e}")

    async def parse(self, response):
        keyword = response.meta.get("keyword")
        page_no = int(response.meta.get("page_no") or 1)
        self._kw_stats.setdefault(keyword, {"pages": 0, "items": 0})
        if page_no > self._kw_stats[keyword]["pages"]:
            self._kw_stats[keyword]["pages"] = page_no
        self.logger.info(f"解析关键词: {keyword} | page={page_no} | url={response.url}")
        self._save_response_html(response)

        results = response.xpath('//li[@class="b_algo"]')

        if not results:
            self.logger.warning(f"关键词 '{keyword}' 未找到结果 | page={page_no}")
            self.mark_finished_bing(keyword)
            next_kw_req = self._next_unfinished_keyword_request()
            if next_kw_req:
                yield next_kw_req
            return

        extracted = 0
        for res in results:
            url = res.xpath('.//h2/a/@href').get()
            title_parts = res.xpath('.//h2/a//text()').getall()
            title = "".join(title_parts).strip()
            
            # Print the extracted data instead of yielding BingFileItem
            print(f"[{keyword}] Extracted URL: {url}")
            print(f"[{keyword}] Extracted Title: {title}")
            print("-" * 50)

            if not url:
                continue

            extracted += 1

        self._kw_stats[keyword]["items"] += extracted
        self.logger.info(f"完成页面: {keyword} | page={page_no} | extracted={extracted}")

        next_page = response.xpath('//a[@title="下一页"]/@href').get() or response.xpath('//a[@title="Next page"]/@href').get()
        if next_page:
            meta = dict(response.meta)
            meta["page_no"] = page_no + 1
            meta["proxy"] = self.proxy_url
            yield response.follow(next_page, callback=self.parse, meta=meta)
        else:
            self.mark_finished_bing(keyword)
            next_kw_req = self._next_unfinished_keyword_request()
            if next_kw_req:
                yield next_kw_req

    def load_keywords(self, path):
        try:
            if not os.path.exists(path):
                self.logger.error(f"关键词文件不存在: {path}")
                return []
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
                return [item['外文'] for item in data if item.get('外文')]
        except Exception as e:
            self.logger.error(f"加载关键词异常: {e}")
            return []
