"""存储层：CSV + SQLite 双后端"""
import csv
import sqlite3
from pathlib import Path


class CsvStorage:
    def __init__(self, path: Path):
        self.path = path

    def save(self, records: list[dict]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = ["title", "author", "rating", "rating_count", "quote", "link"]
        with open(self.path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)


class SqliteStorage:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, records: list[dict]):
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT UNIQUE,
                    author TEXT,
                    rating REAL,
                    rating_count INTEGER,
                    quote TEXT,
                    link TEXT
                )
            """)
            conn.executemany(
                "INSERT OR IGNORE INTO books "
                "(title, author, rating, rating_count, quote, link) "
                "VALUES (:title, :author, :rating, :rating_count, :quote, :link)",
                records,
            )
            conn.commit()
        finally:
            conn.close()
