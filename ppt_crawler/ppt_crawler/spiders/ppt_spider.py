import os
import json
import time
import random
import re
import socket
import logging
import tempfile
from scrapy import Spider, Request
from scrapy.exceptions import CloseSpider
from DrissionPage import Chromium, ChromiumOptions
from ..items import PptItem

logger = logging.getLogger(__name__)


def get_proxy():
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
    return proxies


def create_proxy_extension(proxy_host, proxy_port, proxy_user, proxy_pass):
    """创建处理代理认证的 Chrome 扩展（临时目录），返回扩展路径"""
    ext_dir = tempfile.mkdtemp(prefix='proxy_ext_')

    manifest = {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Proxy Auth Extension",
        "permissions": [
            "proxy", "tabs", "unlimitedStorage", "storage",
            "<all_urls>", "webRequest", "webRequestBlocking"
        ],
        "background": {"scripts": ["background.js"]},
        "minimum_chrome_version": "22.0.0"
    }

    background_js = f"""
var config = {{
    mode: "fixed_servers",
    rules: {{
        singleProxy: {{
            scheme: "http",
            host: "{proxy_host}",
            port: parseInt("{proxy_port}")
        }},
        bypassList: ["localhost", "127.0.0.1"]
    }}
}};

chrome.proxy.settings.set({{value: config, scope: "regular"}}, function(){{}});

chrome.webRequest.onAuthRequired.addListener(
    function(details) {{
        return {{
            authCredentials: {{
                username: "{proxy_user}",
                password: "{proxy_pass}"
            }}
        }};
    }},
    {{urls: ["<all_urls>"]}},
    ["blocking"]
);
"""

    with open(os.path.join(ext_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    with open(os.path.join(ext_dir, 'background.js'), 'w', encoding='utf-8') as f:
        f.write(background_js)

    return ext_dir


class PptSpider(Spider):
    name = 'ppt_spider'
    allowed_domains = ['bing.com']
    start_urls = ['https://cn.bing.com']  # 恢复start_urls

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 初始化基础变量
        self.base_dir = None
        self.finished_json = None
        self.keyword_json = None
        self.file_type = "pptx"
        self.file_type_1 = None
        self.request_delay = None
        self.port_range = None

        self.keywords = []
        self.finished_keywords = []
        self.pending_keywords = []

        # 爬虫状态
        self.browser = None
        self.tab = None
        self.current_keyword = None
        self.current_page = 1
        self.max_pages = 30

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        """Scrapy核心方法：创建Spider实例并绑定配置"""
        spider = super().from_crawler(crawler, *args, **kwargs)

        # 从settings读取配置
        spider.settings = crawler.settings
        spider.base_dir = spider.settings.get('BASE_DIR')
        spider.finished_json = spider.settings.get('FINISHED_JSON')
        spider.keyword_json = spider.settings.get('KEYWORD_JSON')
        spider.file_type = spider.settings.get('FILE_TYPE')
        spider.file_type_1 = spider.settings.get('FILE_TYPE_1')
        spider.request_delay = spider.settings.get('REQUEST_DELAY')
        spider.port_range = spider.settings.get('PORT_RANGE')

        # 初始化目录
        os.makedirs(spider.base_dir, exist_ok=True)

        # 加载关键词（添加兜底逻辑）
        spider._load_keywords()
        spider._load_finished_keywords()
        spider.pending_keywords = [kw for kw in spider.keywords if kw not in spider.finished_keywords]

        # 如果没有关键词，使用默认关键词兜底
        if not spider.pending_keywords:
            default_keywords = ["人工智能", "大数据", "机器学习", "Python教程"]
            spider.pending_keywords = default_keywords
            logger.warning(f"⚠️ 没有待处理的关键词，使用默认关键词: {default_keywords}")

        # 初始化DrissionPage浏览器
        try:
            spider._init_browser()
        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            raise CloseSpider("browser_init_failed")

        return spider

    def start_requests(self):
        """开始请求（标准Scrapy方式）"""
        if self.pending_keywords:
            self.current_keyword = self.pending_keywords.pop(0)
            logger.info(f"🚀 开始处理关键词: {self.current_keyword}")
            # 发送一个空请求，仅用于触发search_keyword回调
            yield Request(
                url='https://cn.bing.com',
                callback=self.search_keyword,
                meta={'keyword': self.current_keyword},
                dont_filter=True
            )
        else:
            logger.info("📭 无待处理关键词")

    def search_keyword(self, response):
        """执行关键词搜索并解析结果（核心修复）"""
        keyword = response.meta['keyword']
        try:
            # 使用DrissionPage操作页面（忽略Scrapy的response）
            self.tab.get('https://cn.bing.com', timeout=30)
            time.sleep(random.uniform(2, 4))

            # 执行搜索
            search_box = self.tab.ele('xpath://input[@name="q"]', timeout=10)
            search_query = f'allintext:"{keyword}" filetype:{self.file_type}'
            search_box.input(search_query, clear=True)
            search_box.input('\n')
            self.tab.wait.load_start(timeout=20)
            time.sleep(random.uniform(*self.request_delay))

            # 处理搜索结果（标准yield方式提交Item）
            self.current_page = 1
            while self.current_page <= self.max_pages:
                # 等待结果加载
                try:
                    self.tab.wait.ele_displayed('xpath://li[@class="b_algo"]', timeout=10)
                except Exception:
                    logger.warning(f"⚠️ 关键词[{keyword}]第{self.current_page}页无搜索结果，结束翻页")
                    break

                # 解析结果并提交Item（核心修复：用yield替代引擎调用）
                item_count = 0
                results = self.tab.eles('xpath://h2/a')

                for result in results:
                    try:
                        url = result.attr('href')
                        title = result.text.strip()

                        if url and title:
                            ext = os.path.splitext(url)[1].lower()
                            if ext in [f'.{self.file_type}', f'.{self.file_type_1}']:
                                # 创建并yield Item（Scrapy标准方式）
                                ppt_item = PptItem()
                                ppt_item['url'] = url
                                ppt_item['filename'] = self._sanitize_filename(title) + ext
                                ppt_item['keyword'] = keyword
                                ppt_item['domain'] = self._classify_domain(url)
                                ppt_item['language'] = None
                                ppt_item['file_hash'] = None

                                yield ppt_item  # ✅ 标准方式：提交Item到管道
                                item_count += 1
                    except Exception as e:
                        logger.warning(f"⚠️ 解析单个结果失败: {e}")
                        continue

                logger.info(f"📄 关键词[{keyword}]第{self.current_page}页发现 {item_count} 个文件")

                # 翻页
                if not self._next_page():
                    break

                self.current_page += 1

            # 标记关键词完成
            self._save_finished_keyword(keyword)
            logger.info(f"✅ 关键词[{keyword}]处理完成")

            # 处理下一个关键词
            if self.pending_keywords:
                next_keyword = self.pending_keywords.pop(0)
                logger.info(f"🔄 处理下一个关键词: {next_keyword}")
                yield Request(
                    url='https://cn.bing.com',
                    callback=self.search_keyword,
                    meta={'keyword': next_keyword},
                    dont_filter=True
                )
            else:
                logger.info("🎉 所有关键词处理完成")

        except Exception as e:
            logger.error(f"❌ 处理关键词 {keyword} 失败: {e}")
            self._save_finished_keyword(keyword)
            # 处理下一个关键词
            if self.pending_keywords:
                next_keyword = self.pending_keywords.pop(0)
                yield Request(
                    url='https://cn.bing.com',
                    callback=self.search_keyword,
                    meta={'keyword': next_keyword},
                    dont_filter=True
                )

    # ========== 以下方法保持不变 ==========
    def _load_keywords(self):
        """加载关键词列表（带详细错误处理）"""
        try:
            logger.info(f"🔍 尝试加载关键词文件: {self.keyword_json}")
            logger.info(f"📂 文件是否存在: {os.path.exists(self.keyword_json)}")

            if not os.path.exists(self.keyword_json):
                logger.warning(f"⚠️ 关键词文件不存在: {self.keyword_json}")
                self.keywords = ["人工智能", "大数据", "机器学习"]
                logger.info(f"✅ 使用默认关键词: {self.keywords}")
                return

            with open(self.keyword_json, 'r', encoding='utf-8-sig') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON格式错误: {e}")
                    self.keywords = ["人工智能", "大数据", "机器学习"]
                    logger.info(f"✅ 使用默认关键词: {self.keywords}")
                    return

            self.keywords = []
            for idx, item in enumerate(data):
                if isinstance(item, dict) and '中文' in item:
                    keyword = item['中文'].strip()
                    if keyword:
                        self.keywords.append(keyword)
                else:
                    logger.warning(f"⚠️ 第{idx + 1}行数据格式错误，跳过: {item}")

            if not self.keywords:
                logger.warning(f"⚠️ 关键词文件中无有效关键词")
                self.keywords = ["人工智能", "大数据", "机器学习"]

            logger.info(f"✅ 加载关键词 {len(self.keywords)} 个: {self.keywords[:5]}...")

        except Exception as e:
            logger.error(f"❌ 加载关键词失败: {type(e).__name__} - {e}")
            self.keywords = ["人工智能", "大数据", "机器学习"]
            logger.info(f"✅ 使用默认关键词: {self.keywords}")

    def _load_finished_keywords(self):
        """加载已完成的关键词"""
        try:
            if os.path.exists(self.finished_json):
                with open(self.finished_json, 'r', encoding='utf-8') as f:
                    self.finished_keywords = json.load(f)
                logger.info(f"✅ 已完成关键词 {len(self.finished_keywords)} 个")
            else:
                self.finished_keywords = []
        except Exception as e:
            logger.warning(f"⚠️ 加载已完成关键词失败，重置为空: {e}")
            self.finished_keywords = []

    def _save_finished_keyword(self, keyword):
        """标记关键词为已完成"""
        try:
            if keyword not in self.finished_keywords:
                self.finished_keywords.append(keyword)
                with open(self.finished_json, 'w', encoding='utf-8') as f:
                    json.dump(self.finished_keywords, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ 保存已完成关键词失败: {e}")

    def _get_available_port(self):
        """获取可用端口"""
        start, end = self.port_range
        ports = list(range(start, end + 1))
        random.shuffle(ports)
        for port in ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    return port
            except OSError:
                continue
        return random.randint(start, end)

    def _init_browser(self):
        """初始化DrissionPage浏览器"""
        try:
            co = ChromiumOptions()
            co.set_local_port(self._get_available_port())
            co.headless()  # 核心：不显示浏览器窗口
            co.set_argument('--headless=new')  # 兼容新版Chrome的无头模式
            co.set_argument('--disable-blink-features=AutomationControlled')
            co.set_argument('--disable-gpu')
            co.set_argument('--no-first-run')
            co.set_argument('--disable-translate')
            co.set_argument('--no-sandbox')
            co.set_argument('--disable-dev-shm-usage')

            # 通过 Chrome 扩展实现带账号密码的代理认证
            proxies = get_proxy()
            proxy_host = "u10097.20.tp.16yun.cn"
            proxy_port = "6447"
            proxy_user = "16XUBUTY"
            proxy_pass = "656882"
            self._proxy_ext_dir = create_proxy_extension(proxy_host, proxy_port, proxy_user, proxy_pass)
            co.add_extension(self._proxy_ext_dir)
            logger.info(f"✅ 代理扩展已加载: {proxies['HTTP']}")

            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            ]
            co.set_user_agent(random.choice(user_agents))

            self.browser = Chromium(co)
            self.tab = self.browser.new_tab()
            logger.info("✅ 浏览器初始化完成")

        except Exception as e:
            logger.error(f"❌ 浏览器初始化失败: {e}")
            raise

    def _sanitize_filename(self, filename):
        """清理文件名非法字符"""
        return re.sub(r'[<>:"/\\|?*]', '_', filename)

    def _classify_domain(self, url):
        """简单域名分类"""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lstrip('www.').lower()
            if 'gov' in domain:
                return 'GOV'
            elif 'edu' in domain:
                return 'EDU'
            elif 'org' in domain:
                return 'ORG'
            else:
                return 'OTHER'
        except Exception:
            return 'OTHER'

    def _next_page(self):
        """翻页逻辑"""
        try:
            next_buttons = self.tab.eles('xpath://a[@aria-label="下一页"]')
            if next_buttons:
                next_buttons[-1].click()
                self.tab.wait.load_start(timeout=15)
                time.sleep(random.uniform(*self.request_delay))
                return True
            return False
        except Exception as e:
            logger.warning(f"⚠️ 翻页失败: {e}")
            return False

    def closed(self, reason):
        """爬虫关闭清理"""
        logger.info(f"🔌 爬虫关闭，原因: {reason}")
        try:
            if self.tab:
                self.tab.close()
            if self.browser:
                self.browser.quit()
            logger.info("✅ 浏览器已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭浏览器失败: {e}")

        try:
            import shutil
            if hasattr(self, '_proxy_ext_dir') and self._proxy_ext_dir:
                shutil.rmtree(self._proxy_ext_dir, ignore_errors=True)
                logger.info("✅ 代理扩展临时目录已清理")
        except Exception as e:
            logger.warning(f"⚠️ 清理代理扩展目录失败: {e}")