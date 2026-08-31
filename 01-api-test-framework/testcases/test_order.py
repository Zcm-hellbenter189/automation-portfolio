"""下单接口用例：完整依赖链 登录 → 创建用户 → 下单"""
from core import assertions
from core.http_client import HttpClient

BASE_URL = "http://127.0.0.1:8000"


def test_place_order_uses_dependency_chain(client, auto_login):
    """依赖链演示：登录取 token → 创建用户取 user_id → 下单

    这是接口自动化的核心难点场景：下游接口依赖上游接口的返回值。
    auto_login 夹具通过变量池把 token / user_id 自动传递到本用例。
    """
    user_id = auto_login.get("user_id")
    resp = client.post("/api/orders", json={
        "user_id": user_id,
        "product": "自动化测试工具",
        "amount": 199,
    })
    assertions.assert_status_code(resp, 200)
    assertions.assert_code(resp, 0)
    assertions.assert_required_fields(resp, ["order_id"])
    assertions.assert_json_field(resp, "amount", expected=199, value_type=int)


def test_place_order_invalid_user(client, auto_login):
    """user_id 不存在时下单应失败"""
    resp = client.post("/api/orders", json={
        "user_id": 99999,
        "product": "x",
        "amount": 1,
    })
    assertions.assert_status_code(resp, 400)
    assertions.assert_code(resp, 1005)


def test_place_order_without_token():
    """未登录下单应返回 401（用独立 client 验证，避免 token 干扰）"""
    unauth = HttpClient(base_url=BASE_URL)
    resp = unauth.post("/api/orders", json={"user_id": 1, "product": "x", "amount": 1})
    assertions.assert_status_code(resp, 401)
