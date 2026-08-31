"""请求层：限速器 + 指数退避重试 + 超时 + UA 标识

合规要点:
  - 单线程串行 + 强制请求间隔（限速）
  - 遇 403/429 立即停止，不绕验证码、不换 IP 硬刚
"""
import time

import requests

from utils.logger import get_logger

logger = get_logger("fetcher")


class RateLimiter:
    """简单的固定间隔限速器"""

    def __init__(self, interval: float = 3.0):
        self.interval = interval
        self._last = 0.0

    def wait(self):
        elapsed = time.time() - self._last
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last = time.time()


class Fetcher:
    def __init__(self, interval: float = 3.0, max_retries: int = 2,
                 timeout: float = 10, user_agent: str = ""):
        self.limiter = RateLimiter(interval)
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.stopped = False  # 触发反爬后置 True，主流程立即停止

    def get(self, url: str) -> requests.Response | None:
        self.limiter.wait()
        for attempt in range(1, self.max_retries + 2):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                # 对未声明 charset 的文本响应按 UTF-8 兜底解码
                # （requests 对 text/* 默认 latin-1，部分站点/本地演示不声明 charset 会乱码）
                if resp.encoding and resp.encoding.lower() == "iso-8859-1":
                    resp.encoding = "utf-8"
                logger.info(f"[GET] {url} -> {resp.status_code}")
                if resp.status_code in (403, 429):
                    logger.warning(f"收到 {resp.status_code}，触发反爬限制，停止采集（合规红线）")
                    self.stopped = True
                    return None
                if resp.status_code == 404:
                    logger.warning(f"页面不存在: {url}")
                    return None
                resp.raise_for_status()
                return resp
            except (requests.Timeout, requests.ConnectionError) as e:
                logger.warning(f"第 {attempt}/{self.max_retries + 1} 次请求失败: {e}")
                if attempt <= self.max_retries:
                    time.sleep(2 ** attempt)  # 指数退避
        return None
