"""HTTP 客户端封装：Session 复用、token 自动注入、超时控制、指数退避重试、请求/响应日志

设计要点:
  - 基于 requests.Session，连接复用，性能好
  - token 为实例属性，登录后 client.token = xxx 即可全局生效
  - 失败自动重试（指数退避），网络抖动不误报
"""
import time

import requests

from utils.logger import get_logger

logger = get_logger("http_client")


class HttpClient:
    def __init__(self, base_url: str, timeout: float = 10, retry_times: int = 0,
                 headers: dict | None = None, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_times = retry_times
        self.session = requests.Session()
        self.session.headers.update(headers or {})
        self.token = token

    def _headers(self) -> dict:
        h = {}
        if self.token:
            h["Authorization"] = self.token
        return h

    def request(self, method: str, path: str, **kwargs):
        """统一请求入口：超时、重试、日志"""
        url = self.base_url + path
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("headers", self._headers())
        attempts = self.retry_times + 1
        last_exc = None
        for i in range(attempts):
            try:
                resp = self.session.request(method, url, **kwargs)
                logger.info(f"[{method}] {path} -> {resp.status_code} "
                            f"{resp.elapsed.total_seconds() * 1000:.0f}ms")
                return resp
            except (requests.Timeout, requests.ConnectionError) as e:
                last_exc = e
                logger.warning(f"[{method}] {path} 第{i + 1}/{attempts} 次失败: {e}")
                if i < attempts - 1:
                    time.sleep(2 ** i)  # 指数退避
        raise last_exc

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.request("DELETE", path, **kwargs)
