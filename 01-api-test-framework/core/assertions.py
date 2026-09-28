"""统一断言库：状态码 / 业务码 / JSON 字段 / 字段类型 / 响应时间 / 必填字段

设计要点:
  - 断言集中管理，用例层写起来简洁、报错信息明确
  - 校验维度: HTTP 状态码 + 业务码 + 字段值 + 字段类型 + 必填字段 + 响应耗时
  - 断言失败时附带响应体摘要，排查问题无需再去翻日志

⚠️ 已知边界（了解即可，暂不修改）:
  - `assert_code` / `assert_json_field` / `assert_required_fields` 直接调用 `resp.json()`：
    遇到**非 JSON 响应**（典型：标准库返回的 HTML 错误页）会抛 `ValueError`，
    而不是给出清晰的断言失败信息；
  - `_body_preview` 里的 `except Exception` 是**故意兜底**（只为取文本，取不到就返回空串）；
  - 字段检查只覆盖 `data` **第一层**，嵌套字段（如 `data.user.id`）需自行拆分。
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
    """断言响应体里的**业务码**（`code` 字段）

    业务码清单见 `mock_server.py` 的模块 docstring（唯一定义处）。
    ⚠️ 注意：本函数对**非 JSON 响应**会抛 `ValueError`（见模块 docstring 的已知边界）。
    """
    data = resp.json() # 把响应的JSON字符串，自动解析成Python字典/列表
    assert data.get("code") == expected_code, \
        f"业务码不符: 实际 {data.get('code')}，期望 {expected_code}{_body_preview(resp)}"


def assert_json_field(resp, field: str, expected=None, value_type=None):
    """断言 data 中某个字段的值和类型

    :param resp: requests 的 Response 对象
    :param field: 字段名（**只查 `data` 第一层**，如 "amount"）
    :param expected: 期望值。⚠️ **传 None 表示"跳过值校验"** —— 所以
                     **无法用它断言"值就是 None"**
    :param value_type: 期望类型（如 `int` / `str`）；传 None 则跳过类型校验
    :return: 该字段的实际值（便于调用方拿到后继续断言）

    校验顺序：① 字段**是否存在** → ② 值是否相等 → ③ 类型是否正确
    """
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

