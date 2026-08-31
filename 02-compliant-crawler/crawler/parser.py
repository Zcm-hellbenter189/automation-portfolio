"""解析层：parsel 提取字段（CSS + XPath 双语法）

换目标站点时，只需重写本类的 SELECTORS 与 parse 方法。
"""
import parsel


class BookParser:
    """解析图书榜单列表页（默认兼容豆瓣读书 Top250 结构）"""

    SELECTORS = {
        "items": "//ol[@class='grid_view']/li",
        "title": "./div[@class='item']//div[@class='hd']//span[@class='title'][1]/text()",
        "author": "./div[@class='item']//div[@class='bd']/p[1]/text()[1]",
        "rating": "./div[@class='item']//span[@class='rating_nums']/text()",
        "rating_count": "./div[@class='item']//span[contains(@class,'pl')]/text()",
        "quote": "./div[@class='item']//span[@class='inq']/text()",
        "link": "./div[@class='item']//div[@class='hd']/a/@href",
    }

    def parse(self, html: str) -> list[dict]:
        selector = parsel.Selector(text=html)
        books = []
        for item in selector.xpath(self.SELECTORS["items"]):
            books.append({
                "title": self._first(item.xpath(self.SELECTORS["title"])),
                "author": self._first(item.xpath(self.SELECTORS["author"])),
                "rating": self._first(item.xpath(self.SELECTORS["rating"])),
                "rating_count": self._first(item.xpath(self.SELECTORS["rating_count"])),
                "quote": self._first(item.xpath(self.SELECTORS["quote"])),
                "link": self._first(item.xpath(self.SELECTORS["link"])),
            })
        return books

    @staticmethod
    def _first(nodes) -> str:
        if not nodes:
            return ""
        return (nodes.get() or "").strip()
