import scrapy
from scrapy import Field

class PptItem(scrapy.Item):
    """PPT文件数据项"""
    url = Field()          # 文件下载链接
    filename = Field()     # 文件名
    keyword = Field()      # 搜索关键词
    domain = Field()       # 域名分类
    language = Field()     # 语言类型
    file_hash = Field()    # 文件哈希值