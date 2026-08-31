"""清洗层：字段清洗、标题去重、数据校验"""
import re


def clean_rating_count(text: str) -> int:
    """' (372574人评价) ' -> 372574"""
    nums = re.findall(r"\d+", text or "")
    return int(nums[0]) if nums else 0


def clean_rating(text: str) -> float:
    try:
        return float(text or 0)
    except ValueError:
        return 0.0


def clean_author(text: str) -> str:
    """'曹雪芹 / 人民文学出版社 / 1996-12' -> '曹雪芹'"""
    if not text:
        return ""
    return text.split("/")[0].replace("\n", "").strip()


class Pipeline:
    """清洗 + 去重（按书名）"""

    def __init__(self):
        self.seen = set()

    def process(self, raw: dict) -> dict | None:
        title = (raw.get("title") or "").strip()
        if not title or title in self.seen:
            return None
        self.seen.add(title)
        return {
            "title": title,
            "author": clean_author(raw.get("author", "")),
            "rating": clean_rating(raw.get("rating")),
            "rating_count": clean_rating_count(raw.get("rating_count")),
            "quote": (raw.get("quote") or "").strip(),
            "link": (raw.get("link") or "").strip(),
        }
