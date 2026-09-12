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

def test_update_user_success(client,created_user):
    uid = created_user["id"]
    old_name,old_age=created_user["name"],created_user["age"]
    # 新值由旧值派生 → 保证与原值必然不同，且不依赖夹具用的具体名字
    new_name=f"{old_name}_已改"
    new_age=old_age+1
    # ① 发更新请求
    resp=client.put(f"/api/users/{uid}",json={"name":new_name,"age":new_age})
    assertions.assert_status_code(resp,200)
    assertions.assert_code(resp,0)
    # ② 响应体里应回显更新后的数据
    assertions.assert_json_field(resp,"name",expected=new_name)
    assertions.assert_json_field(resp,"age",expected=new_age)
    # ③ 关键：再查一次，证明是"真的落库了"而不是只回显
    got_resp=client.get(f"/api/users/{uid}")
    assertions.assert_status_code(got_resp,200)
    assertions.assert_json_field(got_resp,"name",expected=new_name)
    assertions.assert_json_field(got_resp,"age",expected=new_age,value_type=int)
    assertions.assert_json_field(got_resp,"id",expected=uid)



