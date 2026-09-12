"""统一断言库：状态码 / 业务码 / JSON 字段 / 字段类型 / 响应时间 / 必填字段

设计要点:
  - 断言集中管理，用例层写起来简洁、报错信息明确
  - 校验维度: HTTP 状态码 + 业务 code + 字段值 + 字段类型 + 耗时
  - 断言失败时附带响应体摘要，排查问题无需再去翻日志
"""


def _body_preview(resp, limit: int = 160) -> str:
    """截取响应体前 limit 字符作为断言失败的排错上下文"""
    try:
        text = resp.text
    except Exception:
        return ""
    text = (text or "").replace("\n", " ").strip()
    return f" | 响应体: {text[:limit]}" if text else ""


def assert_status_code(resp, expected: int):
    """断言 HTTP 状态码"""
    assert resp.status_code == expected, \
        f"HTTP 状态码不符: 实际 {resp.status_code}，期望 {expected}{_body_preview(resp)}"


def assert_code(resp, expected_code: int):
    """断言业务 code 字段"""
    data = resp.json() # 把响应的JSON字符串，自动解析成Python字典/列表
    assert data.get("code") == expected_code, \
        f"业务 code 不符: 实际 {data.get('code')}，期望 {expected_code}{_body_preview(resp)}"


def assert_json_field(resp, field: str, expected=None, value_type=None):
    """断言 data 中某个字段的值和类型"""
    data = resp.json().get("data", {})
    assert field in data, f"响应 data 中缺少字段: {field}"
    value = data[field]
    if expected is not None:
        assert value == expected, f"字段 [{field}] 值不符: 实际 {value}，期望 {expected}"
    if value_type is not None:
        assert isinstance(value, value_type), \
            f"字段 [{field}] 类型不符: 实际 {type(value).__name__}，期望 {value_type.__name__}"
    return value


def assert_required_fields(resp, fields):
    """断言 data 中包含所有必填字段

    :param resp: requests 的 Response 对象
    :param fields: 必填字段名列表，如 ["id", "name", "age"]
    注意：只校验"键是否存在"，不校验值的类型或是否为空；
         且只检查 data 第一层，嵌套字段（如 data.user.id）需自行拆分。
    """
    # 取响应中的 data 子字典；失败响应可能没有 data，用 {} 兜底避免 KeyError
    data = resp.json().get("data", {})
    # 列表推导式：筛出所有"不在 data 键里"的字段，得到缺失清单
    missing = [f for f in fields if f not in data]
    # 断言缺失清单为空：为空 → 通过；非空 → 抛异常并列出具体缺哪些字段
    assert not missing, f"响应 data 缺少字段: {missing}"


def assert_elapsed_less_than(resp, seconds: float):
    """断言响应耗时低于阈值（性能断言）"""
    elapsed = resp.elapsed.total_seconds()
    assert elapsed < seconds, f"响应耗时超限: {elapsed:.2f}s >= {seconds}s"

