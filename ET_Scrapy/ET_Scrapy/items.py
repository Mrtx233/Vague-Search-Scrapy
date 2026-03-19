import scrapy


class EtScrapyItem(scrapy.Item):
    url = scrapy.Field()          # 原始 Bing 重定向 URL
    keyword = scrapy.Field()       # 关键词
    page_index = scrapy.Field()    # 页码
    status = scrapy.Field()        # 下载状态: success, failed, skipped_exists 等
    filepath = scrapy.Field()       # 本地保存路径
    file_size = scrapy.Field()     # 文件大小（字节）
