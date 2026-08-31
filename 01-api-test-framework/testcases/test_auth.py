"""登录接口用例：数据驱动 + 断言封装"""
import pytest

from core import assertions
from utils.data_loader import load_yaml
from config.loader import BASE_DIR

CASES = load_yaml(BASE_DIR / "data" / "cases.yaml")["login"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_login(client, case):
    """数据驱动登录用例"""
    resp = client.post("/api/login", json=case["payload"])
    expect = case["expect"]

    assertions.assert_status_code(resp, expect["status_code"])

    if resp.status_code == 200:
        assertions.assert_code(resp, expect["code"])
        token = assertions.assert_json_field(resp, "token", value_type=str)
        assert token.startswith("mock-token-"), "token 格式不正确"


def test_login_response_time(client):
    """登录接口性能断言：应快速返回"""
    resp = client.post("/api/login", json={"username": "admin", "password": "123456"})
    assertions.assert_status_code(resp, 200)
    assertions.assert_elapsed_less_than(resp, 2)
