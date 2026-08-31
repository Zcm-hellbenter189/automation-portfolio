"""用户接口用例：鉴权校验、CRUD、边界场景、慢响应"""
import pytest

from core import assertions
from core.http_client import HttpClient
from utils.data_loader import load_yaml
from config.loader import BASE_DIR

CREATE_CASES = load_yaml(BASE_DIR / "data" / "cases.yaml")["create_user"]
BASE_URL = "http://127.0.0.1:8000"


def _unauth_client() -> HttpClient:
    """构造一个未登录的独立客户端（避免 session 级 token 干扰）"""
    return HttpClient(base_url=BASE_URL)


def test_users_require_auth():
    """未登录访问用户列表应返回 401"""
    resp = _unauth_client().get("/api/users")
    assertions.assert_status_code(resp, 401)


@pytest.mark.parametrize("case", CREATE_CASES, ids=[c["name"] for c in CREATE_CASES])
def test_create_user(client, auto_login, case):
    """数据驱动创建用户用例"""
    resp = client.post("/api/users", json=case["payload"])
    expect = case["expect"]

    assertions.assert_status_code(resp, expect["status_code"])

    if resp.status_code == 200:
        assertions.assert_code(resp, expect["code"])
        assertions.assert_required_fields(resp, ["id", "name", "age"])
        assertions.assert_json_field(resp, "age", value_type=int)
        # 写入变量池，供下单依赖链使用
        auto_login.set("user_id", resp.json()["data"]["id"])


def test_get_user_exists(client, auto_login):
    """查询已存在的用户"""
    uid = auto_login.get("user_id")
    resp = client.get(f"/api/users/{uid}")
    assertions.assert_status_code(resp, 200)
    assertions.assert_code(resp, 0)
    assertions.assert_json_field(resp, "id", expected=uid)


def test_get_user_not_found(client, auto_login):
    """查询不存在的用户应返回 404"""
    resp = client.get("/api/users/99999")
    assertions.assert_status_code(resp, 404)
    assertions.assert_code(resp, 1003)


def test_slow_api_within_timeout(client, auto_login):
    """慢响应接口应在超时阈值内返回（性能断言）"""
    resp = client.get("/api/slow")
    assertions.assert_status_code(resp, 200)
    assertions.assert_elapsed_less_than(resp, 10)
