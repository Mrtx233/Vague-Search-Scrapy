import scrapy


class EtScrapyItem(scrapy.Item):
    url = scrapy.Field()           # 原始 Bing 重定向 URL
    real_url = scrapy.Field()      # 解析出的真实下载 URL
    keyword = scrapy.Field()       # 关键词
    page_index = scrapy.Field()    # 页码
    status = scrapy.Field()        # 下载状态: success, failed, skipped_exists 等
    filepath = scrapy.Field()      # 本地保存路径
    filename = scrapy.Field()      # 最终文件名
    file_size = scrapy.Field()     # 文件大小（字节）
    md5 = scrapy.Field()           # 文件 MD5
