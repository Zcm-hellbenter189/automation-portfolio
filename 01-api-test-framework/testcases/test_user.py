"""用户接口用例：鉴权校验、CRUD、边界场景、慢响应"""
import pytest

from core import assertions
from utils.data_loader import load_yaml
from config.loader import BASE_DIR

CREATE_CASES = load_yaml(BASE_DIR / "data" / "cases.yaml")["create_user"]


def test_users_require_auth(unauth_client):
    """未登录访问用户列表应返回 401"""
    resp = unauth_client.get("/api/users")
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


def test_get_user_exists(client, created_user):
    """查询已创建的用户"""
    uid = created_user["id"]
    resp = client.get(f"/api/users/{uid}")
    assertions.assert_status_code(resp, 200)
    assertions.assert_code(resp, 0)
    assertions.assert_json_field(resp, "id", expected=uid)


def test_get_user_not_found(client, auto_login):
    """查询不存在的用户应返回 404"""
    resp = client.get("/api/users/99999")
    assertions.assert_status_code(resp, 404)
    assertions.assert_code(resp, 1003)


@pytest.mark.slow
def test_slow_api_within_timeout(client, auto_login):
    """慢响应接口应在超时阈值内返回（性能断言）

    标记为 slow：该用例请求 /api/slow，Mock 固定睡 3 秒，
    日常开发用 `pytest -m "not slow"` 跳过以提速，CI 全量执行。
    """
    resp = client.get("/api/slow")
    assertions.assert_status_code(resp, 200)
    assertions.assert_elapsed_less_than(resp, 10)
