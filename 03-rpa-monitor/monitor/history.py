"""采样历史：SQLite 持久化，用于环比分析与追溯"""
import sqlite3
from pathlib import Path


class History:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, name TEXT, url TEXT, status INTEGER,
                elapsed REAL, error TEXT
            )
        """)
        return conn

    def save(self, samples: list[dict]):
        conn = self._conn()
        try:
            conn.executemany(
                "INSERT INTO samples (ts, name, url, status, elapsed, error) "
                "VALUES (:timestamp, :name, :url, :status, :elapsed, :error)",
                samples,
            )
            conn.commit()
        finally:
            conn.close()

    def last_for(self, name: str) -> dict | None:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM samples WHERE name=? ORDER BY id DESC LIMIT 1", (name,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
