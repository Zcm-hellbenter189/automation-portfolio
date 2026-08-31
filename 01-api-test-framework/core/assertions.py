"""统一断言库：状态码 / 业务码 / JSON 字段 / 字段类型 / 响应时间 / 必填字段

设计要点:
  - 断言集中管理，用例层写起来简洁、报错信息明确
  - 校验维度: HTTP 状态码 + 业务 code + 字段值 + 字段类型 + 耗时
"""


def assert_status_code(resp, expected: int):
    """断言 HTTP 状态码"""
    assert resp.status_code == expected, \
        f"HTTP 状态码不符: 实际 {resp.status_code}，期望 {expected}"


def assert_code(resp, expected_code: int):
    """断言业务 code 字段"""
    data = resp.json()
    assert data.get("code") == expected_code, \
        f"业务 code 不符: 实际 {data.get('code')}，期望 {expected_code}"


def assert_json_field(resp, field: str, expected=None, value_type=None):
    """断言 data 中某个字段的值和/或类型"""
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
    """断言 data 中包含所有必填字段"""
    data = resp.json().get("data", {})
    missing = [f for f in fields if f not in data]
    assert not missing, f"响应 data 缺少字段: {missing}"


def assert_elapsed_less_than(resp, seconds: float):
    """断言响应耗时低于阈值（性能断言）"""
    elapsed = resp.elapsed.total_seconds()
    assert elapsed < seconds, f"响应耗时超限: {elapsed:.2f}s >= {seconds}s"
