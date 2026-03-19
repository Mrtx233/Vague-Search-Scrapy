import hashlib
import logging
import os
import random
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
import urllib3
from itemadapter import ItemAdapter

logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)


class EtScrapyPipeline:
    def process_item(self, item, spider):
        return item


class FileDownloadPipeline:
    """下载 Bing 结果中的文件，支持解析 ck 跳转页中的真实下载地址。"""

    ALLOWED_EXTENSIONS = {".xlsx", ".xls"}

    def __init__(self, download_dir, timeout=30, max_retries=2, proxy_url=None):
        self.download_dir = Path(download_dir)
        self.timeout = timeout
        self.max_retries = max_retries
        self.proxy_url = proxy_url
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.session = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            download_dir=crawler.settings.get("DOWNLOAD_DIR", "downloads"),
            timeout=crawler.settings.get("DOWNLOAD_TIMEOUT", 30),
            max_retries=crawler.settings.get("DOWNLOAD_MAX_RETRIES", 2),
            proxy_url=crawler.settings.get("DOWNLOAD_PROXY"),
        )

    def open_spider(self, spider):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
        if self.proxy_url:
            self.session.proxies.update({
                "http": self.proxy_url,
                "https": self.proxy_url,
            })
        logger.info("文件下载 Pipeline 已启动，保存目录: %s", self.download_dir)

    def close_spider(self, spider):
        if self.session is not None:
            self.session.close()
            self.session = None
        logger.info("爬虫结束，文件下载 Pipeline 已关闭")

    def extract_real_download_url_with_requests(self, download_link: str) -> str:
        if "www.bing.com/ck" not in download_link:
            return download_link

        try:
            redirect_resp = self.session.get(
                download_link,
                timeout=(5, 15),
                allow_redirects=True,
                verify=False,
            )
            redirect_resp.raise_for_status()

            match = re.search(r'var\s+u\s*=\s*"([^"]+)"', redirect_resp.text)
            if not match:
                raise ValueError("未在 Bing 跳转页中匹配到真实下载地址")

            real_download_link = match.group(1)
            logger.info("成功从 Bing ck 页面提取真实下载地址 | url=%s", download_link)
            return real_download_link
        except Exception as exc:
            logger.warning("Bing 跳转链接处理失败，回退使用原链接 | url=%s | error=%s", download_link, exc)
            return download_link

    def build_temp_filename(self, original_url: str, real_url: str) -> str:
        parsed = urlparse(real_url)
        suffix = Path(parsed.path).suffix.lower()
        if suffix not in self.ALLOWED_EXTENSIONS:
            suffix = Path(urlparse(unquote(original_url)).path).suffix.lower()
        if suffix not in self.ALLOWED_EXTENSIONS:
            suffix = ".xlsx"

        return f"temp_{int(time.time())}_{random.randint(1000, 9999)}{suffix}"

    def is_allowed_file_type(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.ALLOWED_EXTENSIONS

    def download_file(self, url: str, save_path: Path) -> bool:
        for attempt in range(1, self.max_retries + 2):
            try:
                resume_headers = {}
                if save_path.exists():
                    existing_size = save_path.stat().st_size
                    if existing_size > 0:
                        resume_headers["Range"] = f"bytes={existing_size}-"
                        logger.info("断点续传，已下载 %s 字节 | file=%s", existing_size, save_path.name)

                response = self.session.get(
                    url,
                    headers=resume_headers,
                    stream=True,
                    timeout=self.timeout,
                    allow_redirects=True,
                    verify=False,
                )

                if response.status_code == 206:
                    mode = "ab"
                elif response.status_code == 200:
                    mode = "wb"
                else:
                    response.raise_for_status()
                    mode = "wb"

                with open(save_path, mode) as file_obj:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            file_obj.write(chunk)

                logger.info("文件下载成功 | file=%s", save_path.name)
                return True
            except Exception as exc:
                logger.warning(
                    "下载失败，准备重试 | url=%s | attempt=%s/%s | error=%s",
                    url,
                    attempt,
                    self.max_retries + 1,
                    exc,
                )
                if attempt > self.max_retries:
                    break

        if save_path.exists():
            try:
                save_path.unlink()
            except OSError:
                pass
        return False

    def calculate_md5(self, file_path: Path) -> str | None:
        try:
            md5_hash = hashlib.md5()
            with open(file_path, "rb") as file_obj:
                for chunk in iter(lambda: file_obj.read(8192), b""):
                    md5_hash.update(chunk)
            return md5_hash.hexdigest().lower()
        except Exception as exc:
            logger.warning("计算 MD5 失败 | file=%s | error=%s", file_path, exc)
            return None

    def build_final_filename(self, md5_hash: str, temp_path: Path) -> str:
        suffix = temp_path.suffix.lower() or ".xlsx"
        return f"{md5_hash}{suffix}"

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        original_url = adapter.get("url")

        if not original_url:
            return item

        real_url = self.extract_real_download_url_with_requests(original_url)
        adapter["real_url"] = real_url

        temp_filename = self.build_temp_filename(original_url, real_url)
        temp_path = self.download_dir / temp_filename

        if not self.download_file(real_url, temp_path):
            adapter["status"] = "failed"
            return item

        if not self.is_allowed_file_type(temp_path):
            logger.warning("文件类型不符合要求，删除文件 | file=%s", temp_path.name)
            try:
                temp_path.unlink()
            except OSError:
                pass
            adapter["status"] = "invalid_extension"
            return item

        md5_hash = self.calculate_md5(temp_path)
        if not md5_hash:
            try:
                temp_path.unlink()
            except OSError:
                pass
            adapter["status"] = "failed_md5"
            return item

        final_filename = self.build_final_filename(md5_hash, temp_path)
        final_path = self.download_dir / final_filename

        if final_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
            adapter["status"] = "skipped_duplicate_md5"
            adapter["filepath"] = str(final_path)
            adapter["filename"] = final_filename
            adapter["file_size"] = final_path.stat().st_size
            adapter["md5"] = md5_hash
            logger.info("MD5 重复，跳过保存 | file=%s", final_filename)
            return item

        os.replace(temp_path, final_path)

        adapter["status"] = "success"
        adapter["filepath"] = str(final_path)
        adapter["filename"] = final_filename
        adapter["file_size"] = final_path.stat().st_size
        adapter["md5"] = md5_hash
        logger.info("下载完成并按 MD5 命名 | file=%s | size=%s", final_filename, adapter["file_size"])
        return item
