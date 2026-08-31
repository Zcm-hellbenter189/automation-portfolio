"""pytest 全局夹具：
  - client     按 --env 配置创建的 HTTP 客户端（session 级）
  - variables  跨用例共享的变量池（接口依赖传递）
  - auto_login 自动登录 + 准备依赖数据（token / user_id）
"""
import pytest

from config.loader import load_config, load_login
from core.extractor import VariablePool
from core.http_client import HttpClient


def pytest_addoption(parser):
    parser.addoption("--env", action="store", default="dev", help="运行环境: dev/test/prod")


@pytest.fixture(scope="session")
def env(request):
    return request.config.getoption("--env")


@pytest.fixture(scope="session")
def variables():
    return VariablePool()


@pytest.fixture(scope="session")
def client(env):
    cfg = load_config(env)
    return HttpClient(
        base_url=cfg.get("base_url", "http://127.0.0.1:8000"),
        timeout=cfg.get("timeout", 10),
        retry_times=cfg.get("retry_times", 0),
        headers=cfg.get("headers"),
    )


@pytest.fixture(scope="session")
def auto_login(client, variables):
    """自动登录并准备依赖数据：token + user_id（供依赖链用例使用）"""
    login = load_login()
    resp = client.post("/api/login", json=login)
    token = resp.json()["data"]["token"]
    client.token = token
    variables.set("token", token)

    resp2 = client.post("/api/users", json={"name": "依赖用户", "age": 18})
    variables.set("user_id", resp2.json()["data"]["id"])
    return variables
