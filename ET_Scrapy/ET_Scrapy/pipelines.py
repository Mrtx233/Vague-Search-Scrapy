import logging
import os
import re
import requests
from itemadapter import ItemAdapter
from urllib.parse import unquote

logger = logging.getLogger(__name__)


class EtScrapyPipeline:
    def process_item(self, item, spider):
        return item


class FileDownloadPipeline:
    """文件下载 Pipeline，处理 Bing 重定向链接"""

    def __init__(self, download_dir, timeout=30, max_retries=2):
        self.download_dir = download_dir
        self.timeout = timeout
        self.max_retries = max_retries
        os.makedirs(self.download_dir, exist_ok=True)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            download_dir=crawler.settings.get("DOWNLOAD_DIR", "downloads"),
            timeout=crawler.settings.get("DOWNLOAD_TIMEOUT", 30),
            max_retries=crawler.settings.get("DOWNLOAD_MAX_RETRIES", 2),
        )

    def open_spider(self, spider):
        logger.info(f"文件下载 Pipeline 已启动，保存目录: {self.download_dir}")

    def close_spider(self, spider):
        logger.info("爬虫结束，文件下载 Pipeline 已关闭")

    def get_real_url(self, url):
        """跟随重定向获取真实文件 URL"""
        try:
            response = requests.head(
                url,
                allow_redirects=True,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
                }
            )
            # 如果 URL 发生变化，说明有重定向
            if response.url != url:
                return response.url
            return url
        except Exception as e:
            logger.warning(f"获取真实 URL 失败: {url} | 错误: {e}")
            return None

    def extract_filename(self, url, real_url=None):
        """从 URL 中提取文件名"""
        # 优先使用真实 URL
        target_url = real_url or url

        # 尝试从真实 URL 提取 xlsx/xls 文件名
        match = re.search(r'[^/]+\.(xlsx|xls)(?:\?|$)', target_url)
        if match:
            return match.group(0)

        # 如果真实 URL 没有文件名，尝试从 Bing 重定向参数中解码
        if "&u=a1aHR0c" in url:
            try:
                encoded = url.split('&u=a1aHR0c')[1].split('&ntb')[0]
                decoded = unquote(encoded)
                match = re.search(r'[^/]+\.(xlsx|xls)$', decoded)
                if match:
                    return match.group(0)
            except:
                pass

        # 最后使用 URL 的 hash 作为文件名
        url_hash = abs(hash(url)) % 1000000
        return f"download_{url_hash}.xlsx"

    def process_item(self, item, spider):
        """下载文件"""
        adapter = ItemAdapter(item)
        url = adapter.get("url")

        if not url:
            return item

        # 获取真实 URL
        real_url = self.get_real_url(url)
        if not real_url:
            adapter["status"] = "failed_to_get_real_url"
            return item

        # 提取文件名
        filename = self.extract_filename(url, real_url)
        filepath = os.path.join(self.download_dir, filename)

        # 跳过已存在的文件
        if os.path.exists(filepath):
            adapter["status"] = "skipped_exists"
            adapter["filepath"] = filepath
            logger.info(f"⏭ 跳过已存在: {filename}")
            return item

        # 下载文件 - 使用真实 URL 下载
        for retry in range(self.max_retries + 1):
            try:
                response = requests.get(
                    real_url,
                    stream=True,
                    timeout=self.timeout,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
                    }
)


                if response.status_code == 200:
                    with open(filepath, 'wb') as f:
                        for chunk in response.iter_content(8192):
                            f.write(chunk)

                    adapter["status"] = "success"
                    adapter["filepath"] = filepath
                    adapter["file_size"] = os.path.getsize(filepath)
                    logger.info(f"✅ 下载成功: {filename} ({adapter['file_size']} bytes)")
                    return item
                else:
                    logger.warning(f"HTTP {response.status_code}: {filename}")

            except Exception as e:
                logger.warning(f"下载失败 {filename} (尝试 {retry + 1}/{self.max_retries + 1}): {e}")
                if retry < self.max_retries:
                    continue

        adapter["status"] = "failed"
        return item
