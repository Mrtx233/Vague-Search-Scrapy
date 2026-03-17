# Scrapy settings for ppt_crawler project
BOT_NAME = 'ppt_crawler'

SPIDER_MODULES = ['ppt_crawler.spiders']
NEWSPIDER_MODULE = 'ppt_crawler.spiders'

# 并发控制
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1
CONCURRENT_REQUESTS_PER_IP = 1

# 下载延迟
DOWNLOAD_DELAY = 2

# ❗ 关键：删除禁用下载器的配置，使用默认值
# DOWNLOAD_HANDLERS = {}

# 日志配置
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(message)s'

# 禁用robots协议
ROBOTSTXT_OBEY = False

# 管道配置
ITEM_PIPELINES = {
    'ppt_crawler.pipelines.PptDownloadPipeline': 300,
}

# 自定义配置
BASE_DIR = "output"
FINISHED_JSON = f"{BASE_DIR}/finished_keywords.json"
HASH_RECORD_JSON = f"{BASE_DIR}/hash_records.json"
KEYWORD_JSON = "中文.json"
FILE_TYPE = 'pptx'
FILE_TYPE_1 = 'ppt'
MAX_DOWNLOAD_WORKERS = 5
REQUEST_DELAY = (4, 8)
PORT_RANGE = (9500, 9999)
LID_MODEL_PATH = "lid.176.bin"