"""HTTP 客户端封装：Session 复用、token 自动注入、超时控制、指数退避重试、请求/响应日志

设计要点:
  - 基于 requests.Session，连接复用，性能好
  - token 为实例属性，登录后 client.token = xxx 即可全局生效
  - 失败自动重试（指数退避），网络抖动不误报
"""
import json
import time

import requests

from utils.logger import get_logger

logger = get_logger("http_client")

# 日志脱敏：命中以下 key（大小写不敏感）时值替换为 ***
_SENSITIVE_KEYS = {
    "password", "passwd", "token", "secret", "authorization",
    "access_token", "refresh_token", "api_key", "apikey",
}


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

    def _mask(self, value):
        """递归脱敏：dict/list 中命中敏感 key 的值替换为 ***"""
        if isinstance(value, dict):
            return {
                k: ("***" if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS
                    and v not in (None, "") else self._mask(v))
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._mask(v) for v in value]
        return value

    def _log_request(self, method: str, url: str, **kwargs) -> None:
        """发送前日志：方法 / URL / query / 请求体（脱敏）"""
        params = kwargs.get("params")
        payload = kwargs.get("json")
        if payload is None:
            payload = kwargs.get("data")
        detail = f" params={self._mask(params)}" if params else ""
        logger.info(f"[REQUEST] {method} {url}{detail}")
        if payload is not None:
            masked = json.dumps(self._mask(payload), ensure_ascii=False, default=str)
            logger.info(f"[REQUEST BODY] {masked}")

    def _log_response(self, resp) -> None:
        """收到响应后日志：状态码 / URL / 耗时 / 响应体（脱敏）"""
        elapsed_ms = resp.elapsed.total_seconds() * 1000
        logger.info(f"[RESPONSE] {resp.status_code} "
                    f"{resp.request.method} {resp.url} {elapsed_ms:.0f}ms")
        try:
            body = resp.json()
        except ValueError:
            logger.info(f"[RESPONSE BODY] {(resp.text or '')[:1000]}")
        else:
            masked = json.dumps(self._mask(body), ensure_ascii=False, default=str)
            logger.info(f"[RESPONSE BODY] {masked}")

    def request(self, method: str, path: str, **kwargs):
        """统一请求入口：headers 合并、超时、指数退避重试、请求/响应日志

        设计要点:
          - headers 采用「session 级 < 调用方本次请求 < Authorization」合并，
            不再用 setdefault 静默丢弃调用方传入的 headers，鉴权头始终注入；
          - 重试覆盖网络异常（Timeout/ConnectionError）与瞬时服务端 5xx；
          - 最后一次失败直接 raise 原始异常（不再 raise 可能为 None 的 last_exc）；
          - 请求/响应 body 写入日志，敏感字段（password/token/Authorization 等）自动脱敏。
        """
        url = self.base_url + path
        kwargs.setdefault("timeout", self.timeout)

        merged = dict(self.session.headers)
        merged.update(kwargs.pop("headers", None) or {})
        merged.update(self._headers())  # Authorization 优先级最高
        kwargs["headers"] = merged

        self._log_request(method, url, **kwargs)

        attempts = self.retry_times + 1
        for i in range(attempts):
            try:
                resp = self.session.request(method, url, **kwargs)
                self._log_response(resp)
                if resp.status_code >= 500 and i < attempts - 1:
                    logger.warning(f"[{method}] {path} 服务端 {resp.status_code}，"
                                   f"第 {i + 1}/{attempts} 次重试")
                    time.sleep(2 ** i)  # 指数退避
                    continue
                return resp
            except (requests.Timeout, requests.ConnectionError) as e:
                logger.warning(f"[{method}] {path} 第{i + 1}/{attempts} 次失败: {e}")
                if i >= attempts - 1:
                    raise
                time.sleep(2 ** i)  # 指数退避

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.request("DELETE", path, **kwargs)
