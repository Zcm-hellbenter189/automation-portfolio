"""指标采集：对每个监控目标发请求，记录状态码、响应时间、错误原因"""
import time

import requests

from utils.logger import get_logger

logger = get_logger("collector")


class Collector:
    def __init__(self, timeout: float = 10):
        self.timeout = timeout
        self.session = requests.Session()

    def collect(self, target: dict) -> dict:
        url = target["url"]
        name = target.get("name", url)
        expected = target.get("expected_status", 200)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        start = time.time()

        try:
            resp = self.session.get(url, timeout=self.timeout)
            elapsed = round(time.time() - start, 3)
            status = resp.status_code
            error = None if status == expected else f"状态码 {status} != 期望 {expected}"
        except requests.Timeout:
            elapsed = round(time.time() - start, 3)
            status = -1
            error = f"请求超时(>{self.timeout}s)"
        except requests.ConnectionError as e:
            elapsed = round(time.time() - start, 3)
            status = -1
            error = f"连接失败: {type(e).__name__}"

        logger.info(f"{name}: status={status} elapsed={elapsed}s error={error or '-'}")
        return {
            "name": name, "url": url, "status": status,
            "elapsed": elapsed, "error": error, "timestamp": now,
        }
