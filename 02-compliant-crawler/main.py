"""合规爬虫入口

用法:
  python main.py                  默认抓本地演示站点（断网可跑，零风险）
  python main.py --source douban  抓豆瓣读书 Top250（需网络，自动遵守限速与 robots.txt）
  python main.py --limit 2        只抓前 2 页（快速验证）
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

import yaml

from crawler.fetcher import Fetcher
from crawler.parser import BookParser
from crawler.pipeline import Pipeline
from crawler.robots_checker import RobotsChecker
from crawler.storage import CsvStorage, SqliteStorage
from utils.logger import get_logger

BASE_DIR = Path(__file__).resolve().parent
logger = get_logger("crawler")
MOCK_PORT = 9000


def load_settings() -> dict:
    with open(BASE_DIR / "config" / "settings.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run(source: str, limit: int | None) -> int:
    settings = load_settings()
    target = settings["targets"][source]
    polite = settings["politeness"]
    storage_cfg = settings["storage"]

    max_pages = target["max_pages"] if limit is None else limit

    # 1. robots.txt 合规校验（红线，先于任何请求）
    checker = RobotsChecker(polite["user_agent"])
    robots_url = target.get("robots_url")
    if robots_url:
        if not checker.check(robots_url, target["start_url"]):
            logger.error("robots.txt 禁止抓取目标路径，已拒绝运行")
            return 1
        logger.info(f"robots.txt 校验通过: {robots_url}")
    else:
        logger.info("未配置 robots.txt（本地演示站点），跳过校验")

    # 2. 采集（限速 + 重试 + 遇 403/429 即停）
    fetcher = Fetcher(
        interval=polite["request_interval"],
        max_retries=polite["max_retries"],
        timeout=polite["timeout"],
        user_agent=polite["user_agent"],
    )
    parser = BookParser()
    pipeline = Pipeline()

    records = []
    for page in range(max_pages):
        url = target["page_url"].format(start=page * target["page_size"])
        logger.info(f"抓取第 {page + 1}/{max_pages} 页: {url}")
        resp = fetcher.get(url)
        if resp is None:
            if fetcher.stopped:
                logger.warning("触发反爬限制，已停止采集（合规）")
                break
            logger.warning(f"第 {page + 1} 页抓取失败，跳过")
            continue
        for raw in parser.parse(resp.text):
            record = pipeline.process(raw)
            if record:
                records.append(record)
        if fetcher.stopped:
            break

    # 3. 存储（CSV + SQLite 双后端）
    csv_storage = CsvStorage(BASE_DIR / storage_cfg["csv_path"])
    sqlite_storage = SqliteStorage(BASE_DIR / storage_cfg["sqlite_path"])
    csv_storage.save(records)
    sqlite_storage.save(records)

    logger.info(f"采集完成: 共 {len(records)} 条")
    logger.info(f"CSV 输出: {csv_storage.path}")
    logger.info(f"SQLite 输出: {sqlite_storage.path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="合规爬虫")
    parser.add_argument("--source", choices=["mock", "douban"], default="mock",
                        help="采集源: mock=本地演示站点, douban=豆瓣读书 Top250")
    parser.add_argument("--limit", type=int, default=None, help="只抓前 N 页")
    args = parser.parse_args()

    if args.source == "mock":
        python = sys.executable
        mock = subprocess.Popen(
            [python, str(BASE_DIR / "mock_site" / "serve.py"), "--port", str(MOCK_PORT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(1.5)  # 等待站点就绪
            return run(args.source, args.limit)
        finally:
            mock.terminate()
            mock.wait()
            print("[*] 演示站点已关闭")
    return run(args.source, args.limit)


if __name__ == "__main__":
    sys.exit(main())
