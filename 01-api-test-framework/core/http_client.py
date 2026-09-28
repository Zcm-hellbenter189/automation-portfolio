"""HTTP 客户端封装：Session 复用、token 自动注入、超时控制、**幂等重试**、请求/响应日志

设计要点:
  - 基于 requests.Session，连接复用，性能好
  - token 为实例属性，登录后 client.token = xxx 即可全局生效
  - **重试只对「幂等方法」自动生效**（共 6 个：GET / HEAD / OPTIONS / TRACE / PUT / DELETE）——
    它们重复执行 N 次与执行 1 次效果相同，可安全重试；
    **POST 等非幂等方法默认不重试**，因为"请求发出去了但响应丢了"的情况下重试会真的
    创建两份数据（重复下单 / 重复注册）。确需重试时由调用方显式传
    retry_non_idempotent=True 自行承担风险（详见下方 _IDEMPOTENT_METHODS 常量的说明）。
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

# HTTP 语义上「幂等」的方法集合：重复执行 N 次与执行 1 次的效果相同。
# 依据 RFC 9110（HTTP 语义）——安全方法（GET/HEAD/OPTIONS/TRACE）+ 幂等方法（PUT/DELETE）。
# **POST 不在其中**：它通常用于"创建"，服务端一般不会去重。
# 注意：这里只按「方法」判断，是保守的通用策略；某个具体 POST 接口若自带幂等键，
#      调用方可显式传 retry_non_idempotent=True 覆盖。
#frozenset = 不可变集合（冻结集合）;frozenset 一旦创建，不能增、删、改元素
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE", "PUT", "DELETE"})


class HttpClient:
    def __init__(self, base_url: str, timeout: float = 10, retry_times: int = 0,
                 headers: dict | None = None, token: str | None = None):
        self.base_url = base_url.rstrip("/") # 去除尾部斜杠
        self.timeout = timeout
        self.retry_times = retry_times
        self.session = requests.Session()
        self.session.headers.update(headers or {})
        self.token = token

    def _headers(self) -> dict:
        """构造本次请求要注入的自定义请求头（目前只有鉴权头）

        :return: token 存在时返回 {"Authorization": token}，否则返回空 dict
        说明：token 是实例属性，由 conftest 的 auto_login 在登录成功后赋值；
             未登录时返回空 dict，等价于"不带鉴权信息"。
        """
        h = {}
        # 已登录（token 有值）才注入 Authorization
        if self.token:
            h["Authorization"] = self.token
        return h

    def _mask(self, value):
        """递归脱敏：把 dict / list 中命中的敏感字段值替换为 ***

        :param value: 任意 JSON 值（dict / list / 标量）
        :return: 结构相同、敏感值被替换后的【新对象】（不修改原对象）
        判定规则：key 名（转小写后）命中模块顶部 _SENSITIVE_KEYS 即脱敏；
                 值为 None 或空字符串时跳过（本身无信息量）。
        局限：列表元素没有 key，只能整体递归，无法按字段名判定。
        """
        if isinstance(value, dict):
            # 字典：逐 key 判断是否敏感；不敏感的值继续递归往里找
            return {
                k: ("***" if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS
                    and v not in (None, "") else self._mask(v))
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            # 列表/元组：元素自身没有 key，只能逐个递归处理
            return [self._mask(v) for v in value]
        # 标量（str / int / None ...）：无法再往下查，原样返回
        return value

    def _log_request(self, method: str, url: str, **kwargs) -> None:
        """发送前日志：方法 / URL / query / 请求体（敏感字段已脱敏）

        :param kwargs: 与 requests 的请求参数一致（json / data / params 等）
        输出示例：
          [REQUEST]      POST http://127.0.0.1:8000/api/login
          [REQUEST BODY] {"username": "admin", "password": "***"}
        """
        params = kwargs.get("params")     # URL 查询参数，如 ?page=1&size=10
        payload = kwargs.get("json")      # JSON 请求体（优先取它）
        if payload is None:
            payload = kwargs.get("data")  # 没有 json 时退而取表单/原始 body
        # 仅当带 query 时才拼这个后缀，避免出现无意义的 " params=None"
        detail = f" params={self._mask(params)}" if params else ""
        logger.info(f"[REQUEST] {method} {url}{detail}")
        if payload is not None:
            # 手动 serialize：ensure_ascii=False 保留中文；default=str 兜底不可序列化类型
            masked = json.dumps(self._mask(payload), ensure_ascii=False, default=str)
            logger.info(f"[REQUEST BODY] {masked}")

    def _log_response(self, resp) -> None:
        """收到响应后日志：状态码 / URL / 耗时 / 响应体（脱敏）"""
        elapsed_ms = resp.elapsed.total_seconds() * 1000
        logger.info(f"[RESPONSE] {resp.status_code} "
                    f"{resp.request.method} {resp.url} {elapsed_ms:.0f}ms")
        try:
            body = resp.json() # 把响应的JSON字符串，自动解析成Python字典/列表
        except ValueError:
            logger.info(f"[RESPONSE BODY] {(resp.text or '')[:1000]}")
        else:
            #json.dumps() 把py对象(字典) → json字符串，default=str默认字符串兜底
            masked = json.dumps(self._mask(body), ensure_ascii=False, default=str)
            logger.info(f"[RESPONSE BODY] {masked}")

    def request(self, method: str, path: str, retry_non_idempotent: bool = False, **kwargs):
        """统一请求入口：headers 合并、超时、指数退避重试、请求/响应日志

        设计要点:
          - headers 采用「session 级 < 调用方本次请求 < Authorization」合并，
            不再用 setdefault 静默丢弃调用方传入的 headers，鉴权头始终注入；
          - **重试有前提**：只对幂等方法（GET/HEAD/OPTIONS/TRACE/PUT/DELETE）自动重试；
            非幂等方法（典型 POST）默认**只发一次** —— 避免"请求其实到了、只是响应丢了"
            的情况下重试，真的创建出两份数据（重复下单 / 重复注册）；
          - 重试覆盖网络异常（Timeout/ConnectionError）与瞬时服务端 5xx；
          - 最后一次失败直接 raise 原始异常（不再 raise 可能为 None 的 last_exc）；
          - 请求/响应 body 写入日志，敏感字段（password/token/Authorization 等）自动脱敏。

        :param method: HTTP 方法名（大小写不敏感）
        :param path: 相对路径，如 "/api/login"（内部会拼到 base_url 之后）
        :param retry_non_idempotent: 是否允许对**非幂等方法**重试，默认 False。
            仅当调用方**明确知道**该接口重复执行是安全的（例如请求体里带了幂等键、
            或服务端本身做了去重）时才传 True —— 这是一次"显式的责任转移"：
            框架默认保守，风险由知情的一方主动承担。
        :param kwargs: 其余参数原样透传给 requests（json / data / params / headers ...）
        """
        url = self.base_url + path
        # 如果没有传入超时时间，则使用默认超时时间
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self.timeout

        merged = dict(self.session.headers)
        merged.update(kwargs.pop("headers", None) or {}) # pop(key, default)：从字典`kwargs`中取出`headers`键，**同时把这个键从 kwargs 里删掉**
        merged.update(self._headers())  # Authorization 优先级最高
        kwargs["headers"] = merged

        self._log_request(method, url, **kwargs) # 打印请求日志

        # ---- 决定本次请求允许几次尝试 ----
        # 幂等方法（GET/PUT/DELETE...）→ 沿用配置的 retry_times；
        # 非幂等方法（POST）→ 降为 1 次（即不重试），除非调用方显式放行。
        # method.upper()，转成大写字母
        allow_retry = retry_non_idempotent or method.upper() in _IDEMPOTENT_METHODS
        if allow_retry:
            attempts = self.retry_times + 1
        else:
            attempts = 1
            if self.retry_times > 0:
                # 让"跳过了重试"这件事可见 —— 否则排障时只看到"没重试"，却不知道为什么
                logger.info(f"[{method}] {path} 是非幂等方法，本次不做自动重试"
                            f"（已配置的 retry_times={self.retry_times} 被跳过）")

        for i in range(attempts):
            try:
                """
                resp = self.session.request(method, url, **kwargs)
                把"请求方法和请求路径"以及请求头和请求体等信息发给服务器；
                服务器的父类读请求行解析出方法名，按 do_+方法名 的约定反射调用 do_POST；
                do_POST再按self.path分发到具体业务——"自动识别"=标准库的方法名约定+你的路径分支。
                客户端和服务端能对上，靠的是共同遵守 HTTP 协议报文格式
                """
                resp = self.session.request(method, url, **kwargs) # 发送请求
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
                    raise #raise：主动抛出异常，把错误向上抛出去，交给上层调用者处理；当前函数直接终止。
                time.sleep(2 ** i)  # 指数退避

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.request("DELETE", path, **kwargs)
