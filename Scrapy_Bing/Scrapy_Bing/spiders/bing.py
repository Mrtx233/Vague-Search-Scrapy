import scrapy


class BingSpider(scrapy.Spider):
    name = "bing"
    allowed_domains = ["bing.com"]

    async def start(self):
        from urllib.parse import quote

        q = "外部经济 filetype:xlsx"
        url = f"https://www.bing.com/search?q={quote(q)}"
        # 使用 Playwright 下载处理器
        yield scrapy.Request(
            url=url,
            callback=self.parse,
            dont_filter=True,
            meta={
                "playwright": True,
                "playwright_include_page": False,
            }
        )

    def parse(self, response):
        print(f"status={response.status} url={response.url}")

        # 保存响应内容到文件，方便查看
        with open("response.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        print("响应内容已保存到 response.html")
        next_page = response.xpath('//a[@title ="下一页"]/@href').getall()
        print(f"//a[@title =\"下一页\"]/@href -> {next_page}")
