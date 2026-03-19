# Scrapy settings for Scrapy_Bing project
import os
import random

BOT_NAME = "Scrapy_Bing"

SPIDER_MODULES = ["Scrapy_Bing.spiders"]
NEWSPIDER_MODULE = "Scrapy_Bing.spiders"

# 1. 随机 User-Agent 列表
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
]

USER_AGENT = random.choice(USER_AGENTS)

# 2. 随机 Accept-Language 列表
ACCEPT_LANGUAGES = [
    'zh-CN,zh;q=0.9,en;q=0.8',
    'zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7',
    'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'en-US,en;q=0.9,zh-CN;q=0.8',
    'zh-TW,zh;q=0.9,en;q=0.8',
]

# 3. 随机 Accept 列表
ACCEPT_HEADERS = [
    'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
]

# 4. 默认 Headers（会被中间件随机化）
DEFAULT_REQUEST_HEADERS = {
    'Accept': random.choice(ACCEPT_HEADERS),
    'Accept-Language': random.choice(ACCEPT_LANGUAGES),
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
}

# 5. 遵守 robots.txt
ROBOTSTXT_OBEY = False

# 6. 启用下载中间件（随机化 headers）
DOWNLOADER_MIDDLEWARES = {
    'Scrapy_Bing.middlewares.ScrapyBingDownloaderMiddleware': 543,
}

# 7. 配置并发与延迟 (模拟真人低频操作)
CONCURRENT_REQUESTS = 1
DOWNLOAD_DELAY = 10  # 基础延迟 10 秒
RANDOMIZE_DOWNLOAD_DELAY = True # 随机延迟

# 8. 启用 Item Pipelines (按顺序执行)
ITEM_PIPELINES = {
    "Scrapy_Bing.pipelines.FileProcessingPipeline": 50,     # 1. 生成基础信息
    "Scrapy_Bing.pipelines.RedisDeduplicatePipeline": 100, # 2. URL 去重
    "Scrapy_Bing.pipelines.CustomBingFilesPipeline": 200,  # 3. 文件下载
    "Scrapy_Bing.pipelines.RedisMD5DeduplicatePipeline": 250,# 4. MD5 去重
    "Scrapy_Bing.pipelines.RedisStoragePipeline": 300,      # 5. 存储结果
}

# 9. 语言检测与域名分类配置
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))
DOMAIN_CONFIG_PATH = os.path.join(_PROJECT_ROOT, 'url_class_keywords.json')
LANGUAGE_MODEL_PATH = os.path.join(_PROJECT_ROOT, 'lid.176.bin')
LANGUAGE_CONFIDENCE_THRESHOLD = 0.8
JSON_STORE_DIR = os.path.join(_PACKAGE_ROOT, 'json')

# 10. 文件存储路径
FILES_STORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'downloads')

# 11. 日志设置
LOG_LEVEL = 'INFO'
LOG_ENCODING = 'utf-8'

FEED_EXPORT_ENCODING = "utf-8"
