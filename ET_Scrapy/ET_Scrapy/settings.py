# Scrapy settings for ET_Scrapy project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "ET_Scrapy"

SPIDER_MODULES = ["ET_Scrapy.spiders"]
NEWSPIDER_MODULE = "ET_Scrapy.spiders"

ADDONS = {}


# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = "ET_Scrapy (+http://www.yourdomain.com)"

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

# Concurrency and throttling settings
#CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 1

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "ET_Scrapy.middlewares.EtScrapySpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    "ET_Scrapy.middlewares.EtScrapyDownloaderMiddleware": 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
ITEM_PIPELINES = {
    "ET_Scrapy.pipelines.FileDownloadPipeline": 300,
}

# 文件下载配置
DOWNLOAD_DIR = "downloads"          # 下载保存目录
DOWNLOAD_TIMEOUT = 30               # 下载超时（秒）
DOWNLOAD_MAX_RETRIES = 2            # 最大重试次数
DOWNLOAD_PROXY = "http://127.0.0.1:7897"  # requests 下载阶段使用的代理

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"

# ==================== Scrapy-Playwright 配置 ====================

# 启用 scrapy-playwright 的下载处理器
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

# 使用异步 reactor（playwright 必需）
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# 浏览器类型
PLAYWRIGHT_BROWSER_TYPE = "chromium"

# Playwright 启动选项
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,  # 无头模式，如需调试可设为 False
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ],
}

# 日志级别设置
LOG_LEVEL = "INFO"  # 只显示 INFO 及以上级别的日志，屏蔽 DEBUG

# 屏蔽 asyncio 的错误输出
LOG_FILTERS = {
    "asyncio": "ERROR",
}
