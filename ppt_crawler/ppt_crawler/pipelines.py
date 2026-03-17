import os
import json
import time
import hashlib
import logging
import threading
import requests
import urllib3
import urllib.parse
import fasttext
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings()
logger = logging.getLogger(__name__)

# 全局锁
hash_lock = threading.Lock()
_counter = 0
_counter_lock = threading.Lock()


class PptDownloadPipeline:
    def __init__(self, settings):
        # 从配置读取参数
        self.base_dir = settings.get('BASE_DIR')
        self.finished_json = settings.get('FINISHED_JSON')
        self.hash_record_json = settings.get('HASH_RECORD_JSON')
        self.max_workers = settings.get('MAX_DOWNLOAD_WORKERS')
        self.file_type = settings.get('FILE_TYPE')
        self.file_type_1 = settings.get('FILE_TYPE_1')

        # 初始化目录
        os.makedirs(self.base_dir, exist_ok=True)

        # 加载语言模型
        self.lid_model = None
        self._load_lid_model(settings.get('LID_MODEL_PATH'))

        # 加载已存在的哈希
        self.existing_hashes = self._load_existing_hashes()

        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def _load_lid_model(self, model_path):
        """加载语言检测模型"""
        try:
            if not os.path.exists(model_path):
                logger.error(f"语言模型文件不存在: {model_path}")
                logger.info("下载地址：https://fasttext.cc/docs/en/language-identification.html")
                return

            fasttext.FastText.eprint = lambda x: None
            self.lid_model = fasttext.load_model(model_path)
            logger.info("✅ 语言检测模型加载成功")
        except Exception as e:
            logger.error(f"加载语言模型失败: {e}")

    def _generate_snowflake_id(self):
        """生成11位不重复雪花ID"""
        global _counter
        with _counter_lock:
            _counter = (_counter + 1) % 10

        timestamp = int(time.time() * 1000) % 100000000
        pid = os.getpid() % 100
        snowflake_id = int(f"{timestamp:08d}{pid:02d}{_counter:d}")
        return snowflake_id if len(str(snowflake_id)) == 11 else snowflake_id % 100000000000

    def _load_existing_hashes(self):
        """加载已下载文件哈希"""
        hashes = set()
        if os.path.exists(self.hash_record_json):
            try:
                with open(self.hash_record_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data.get('result', []):
                        if item.get('hash'):
                            hashes.add(item['hash'])
            except Exception as e:
                logger.error(f"加载哈希记录失败: {e}")
        return hashes

    def _save_hash_record(self, url, file_hash):
        """保存哈希记录"""
        with hash_lock:
            if os.path.exists(self.hash_record_json):
                try:
                    with open(self.hash_record_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception:
                    data = {"type": "wpp", "result": []}
            else:
                data = {"type": "wpp", "result": []}

            # 去重
            for item in data['result']:
                if item.get('hash') == file_hash:
                    return

            data['result'].append({"url": url, "hash": file_hash})
            with open(self.hash_record_json, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def _get_domain_from_url(self, url):
        """提取域名"""
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.netloc.lstrip('www.')
        except Exception:
            return ""

    def _classify_domain(self, url):
        """域名分类"""
        domain = self._get_domain_from_url(url).lower()
        URL_CLASS_KEYWORDS = {
            "GOV": [
                "gov", "gouv", "gob", "gov.cn", "gov.uk", "gov.au", "gob.mx", "gov.sk",
                "iuventa.sk", "ministerio", "dept", "agency", "state", "federal", "municipio", "prefecture",
                "govt", "government", "county", "cityhall", "municipal", "provincial", "regulatory",
                "authority", "federalreserve", "irs", "fbi", "garda", "police.uk", "gc.ca", "govt.nz",
                "bund.de", "kementerian", "presidency", "parliament", "congress", "senate", "council"
            ],
            "EDU": [
                "edu", "ac", "university", "college", "institute", "academic", "research", "science",
                "edu.cn", "ac.uk", "edu.au", "uni.", "polytechnic", "scholar", "professor", "lab", "campus",
                "school", "kindergarten", "preschool", "highschool", "middleschool", "primaryschool",
                "vocational", "technicalschool", "academy", "faculty", "thesis", "dissertation",
                "scholarship", "student", "alumni", "tutor", "mentor", "curriculum", "semester", "credit",
                "degree", "certificate", "phd", "master", "bachelor", "department"
            ],
            "EDUCOMM": [
                "coursera", "udemy", "edx", "mooc", "khanacademy", "futurelearn", "skillshare",
                "pluralsight", "udacity", "udemycdn", "linkedinlearning", "codecademy", "lynda",
                "treehouse", "datacamp", "opensap", "masterclass", "skillsoft", "open2study", "alison",
                "udemyforbusiness", "codewars", "freecodecamp", "edmodo", "classdojo", "duolingo",
                "memrise", "babbel", "busuu", "lingoda", "edxforbusiness", "pluralsightone", "codecademypro"
            ],
            "ORG": [
                "un.org", "who.int", "unesco", "imf", "ilo", "worldbank", "ngo", "wto",
                "icrc", "org", "redcross", "oxfam", "greenpeace", "amnesty", "transparency.org",
                "icj", "icc", "union", "association", "alliance", "council", "forum",
                "oecd", "g20", "asean", "nato", "fao", "rotary", "lionsclub", "charity", "foundation",
                "trust", "coalition", "network", "initiative", "movement", "society", "msf", "care",
                "billgatesfoundation", "rockefellerfoundation", "gatesfoundation", "wef", "club"
            ],
            "WIKI": [
                "wikipedia", "wikidata", "wiktionary", "baike.baidu", "hudong", "citizendium",
                "encarta", "britannica", "factmonster", "infoplease", "scribd",
                "wikiwand", "fandom", "wikisource", "wikimedia", "wikinews", "wikiversity",
                "encyclopedia", "columbiaencyclopedia", "worldbook", "grolier", "sogoubaike", "360baike",
                "wikipediafoundation", "baiduencyclopedia"
            ],
            "NEWS": [
                "bbc", "cnn", "reuters", "xinhuanet", "nytimes", "dw.com", "guardian", "ft.com",
                "bloomberg", "cnbc", "apnews", "aljazeera", "huffpost", "vox.com", "wsj.com",
                "time.com", "economist", "thetimes", "telegraph", "chinatimes", "japantimes",
                "nbcnews", "abcnews", "cbsnews", "foxnews", "msnbc", "usa today", "latimes", "washingtonpost",
                "atlantic", "newyorker", "nationalgeographic", "sciencemag", "nature", "chinadaily",
                "globaltimes", "southchinamorningpost", "asahishimbun", "yomiurishimbun", "afp",
                "people.com.cn", "cctv.com", "凤凰网", "澎湃新闻", "界面新闻"
            ],
            "COMMERCE": [
                "amazon", "ebay", "alibaba", "taobao", "jd.com", "shop", "mall", "retail", "bestbuy",
                "walmart", "tmall", "flipkart", "rakuten", "mercadolibre",
                "ecommerce", "shopify", "etsy", "zappos", "sephora", "macys", "target", "costco",
                "aldi", "lidl", "carrefour", "newegg", "pinduoduo", "suning", "gome", "shein", "asos",
                "zara", "h&m", "uniqlo", "nike", "adidas", "paypal", "stripe", "shopee", "lazada",
                "coupang", "mercado", "wayfair", "overstock", "chewy", "dell", "hp", "apple", "samsung"
            ],
            "SOCIAL": [
                "facebook", "twitter", "instagram", "linkedin", "tiktok", "wechat", "weibo", "snapchat",
                "reddit", "pinterest", "discord", "telegram", "quora",
                "whatsapp", "qq", "douban", "xiaohongshu", "bilibili", "tumblr", "flickr", "vimeo",
                "twitch", "medium", "slack", "microsoftteams", "signal", "mastodon", "mewe", "parler",
                "periscope", "vine", "foursquare", "goodreads", "letterboxd", "behance", "dribbble",
                "kuaishou", "xiaohongshu", "douyin", "kwai", "line", "kakao"
            ]
        }
        for category, keywords in URL_CLASS_KEYWORDS.items():
            if any(kw in domain for kw in keywords):
                return category
        return "OTHER"

    def _detect_language(self, title):
        """检测语言"""
        try:
            if not title or not self.lid_model:
                return None
            pred = self.lid_model.predict(title.strip(), k=1)
            return pred[0][0].replace('__label__', '')
        except Exception as e:
            logger.warning(f"语言检测失败: {e}")
            return "zh" if '\u4e00' <= title <= '\u9fff' else "en"

    def _download_file(self, item):
        """下载文件核心逻辑"""
        url = item['url']
        filename = item['filename']
        keyword = item['keyword']

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Referer': 'https://cn.bing.com/'
        }

        base_dir = ""
        try:
            logger.info(f"🔍 检查文件: {filename}")
            # 下载文件内容
            with requests.get(url, headers=headers, stream=True, timeout=30, verify=False) as r:
                r.raise_for_status()
                file_content = b''
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        file_content += chunk

            # 计算哈希去重
            file_hash = hashlib.md5(file_content).hexdigest()
            if file_hash in self.existing_hashes:
                logger.info(f"⚠️ 哈希已存在，跳过: {file_hash} -> {filename}")
                return

            # 生成存储目录
            snowflake_id = self._generate_snowflake_id()
            base_dir = os.path.join(self.base_dir, str(snowflake_id))
            master_dir = os.path.join(base_dir, 'master')
            meta_dir = os.path.join(base_dir, 'meta')
            os.makedirs(master_dir, exist_ok=True)
            os.makedirs(meta_dir, exist_ok=True)

            # 保存文件
            file_ext = os.path.splitext(filename)[1].lower() or f'.{self.file_type}'
            file_path = os.path.join(master_dir, f"{file_hash}{file_ext}")
            with open(file_path, 'wb') as f:
                f.write(file_content)

            # 生成元数据
            meta_data = {
                "webSite": self._get_domain_from_url(url),
                "crawlTime": int(time.time() * 1000),
                "srcUrl": url,
                "title": filename,
                "hash": file_hash,
                "extend": {
                    "publishTime": None,
                    "keyword": keyword,
                    "language": self._detect_language(filename),
                    "doMain": self._classify_domain(url),
                    "type": file_ext.lstrip('.')
                }
            }

            # 保存元数据
            meta_file = os.path.join(meta_dir, 'metadata.json')
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)

            # 更新哈希记录
            self._save_hash_record(url, file_hash)
            self.existing_hashes.add(file_hash)

            logger.info(f"✅ 下载成功: {file_path}")
            logger.info(f"📄 元数据: {meta_file}")

        except Exception as e:
            logger.error(f"❌ 下载失败 {filename}: {e}")
            # 清理临时目录
            if base_dir and os.path.exists(base_dir):
                import shutil
                shutil.rmtree(base_dir, ignore_errors=True)

    def process_item(self, item, spider):
        """处理每个Item（提交到线程池下载）"""
        self.executor.submit(self._download_file, item)
        return item

    def close_spider(self, spider):
        """爬虫关闭时清理"""
        self.executor.shutdown(wait=True)
        logger.info("✅ 下载线程池已关闭")

        # 统计结果
        total_hashes = len(self._load_existing_hashes())
        logger.info(f"\n========== 爬虫完成 ==========")
        logger.info(f"📁 存储目录: {self.base_dir}")
        logger.info(f"📊 累计唯一文件数: {total_hashes}")
        logger.info(f"📋 哈希记录: {self.hash_record_json}")