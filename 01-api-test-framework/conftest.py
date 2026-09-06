"""pytest 全局夹具：
  - env             --env 参数（dev/test/prod）
  - client          按 --env 配置创建的 HTTP 客户端（session 级，复用连接）
  - unauth_client   未登录客户端（负向鉴权用例用，遵守 --env 配置）
  - auto_login      session 级自动登录 + 准备依赖数据（token / user_id）
  - created_user    每用例独立创建用户（消除用例间隐式顺序耦合）
"""
import pytest

from config.loader import load_config, load_login
from core.extractor import VariablePool, extract_variables
from core.http_client import HttpClient


def pytest_addoption(parser):
    parser.addoption(
        "--env", action="store", default="dev",
        help="运行环境，取 config.yaml 顶层 key（默认 dev；拼错会在用例收集/装配时报错）",
    )


@pytest.fixture(scope="session")
def env(request):
    '''获取 --env 参数，用于加载不同环境的配置文件'''
    return request.config.getoption("--env")
    # request是 pytest 内置的一个特殊 fixture 对象（全名 pytest.FixtureRequest）。
    # 每个 fixture 函数/测试函数都可以声明它
    # request身上最有用的几个属性：
    # request.config          # 整个 pytest 的配置对象（Config）
    # request.config.getoption("--env")   # 读取命令行传入的 --env 值
    # request.scope           # 当前 fixture 的作用域，如 "session"
    # request.module          # 正在运行的测试模块
    # request.cls            # 正在运行的测试类
    # request.function        # 正在运行的测试函数

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
def unauth_client(env):
    """未登录客户端：鉴权负向用例使用，遵守 --env 配置，不受 session token 干扰"""
    cfg = load_config(env)
    return HttpClient(
        base_url=cfg.get("base_url", "http://127.0.0.1:8000"),
        timeout=cfg.get("timeout", 10),
    )


@pytest.fixture(scope="session")
def auto_login(client):
    """session 级自动登录 + 准备依赖数据（token / user_id）

    返回线程安全变量池（接口依赖传递的载体）。
    使用 extract_variables 按路径提取响应字段（响应提取能力真正落地）；
    失败时输出带 base_url / 状态码 / 响应体的可读报错，
    避免原始 KeyError / ConnectionError 掩盖真实原因。
    """
    pool = VariablePool()

    login = load_login()
    resp = client.post("/api/login", json=login)
    assert resp.status_code == 200, (
        f"前置登录失败，依赖 auto_login 的用例将全部无法执行。"
        f"请确认 Mock 服务已启动且账号正确 | "
        f"base_url={client.base_url} status={resp.status_code} body={resp.text[:200]}"
    )
    token = extract_variables(resp, {"token": "data.token"})["token"]
    assert token, f"登录响应缺少 token: {resp.text[:200]}"
    client.token = token
    pool.set("token", token)

    # 准备一个依赖用户（user_id），供「下单依赖链」用例使用
    resp2 = client.post("/api/users", json={"name": "依赖用户", "age": 18})
    assert resp2.status_code == 200, (
        f"准备依赖用户失败，依赖 user_id 的用例将无法执行 | "
        f"status={resp2.status_code} body={resp2.text[:200]}"
    )
    pool.set("user_id", extract_variables(resp2, {"user_id": "data.id"})["user_id"])
    return pool


@pytest.fixture()
def created_user(client, auto_login):
    """每个用例独立创建的用户（显式依赖，无跨用例顺序耦合）"""
    resp = client.post("/api/users", json={"name": "张三", "age": 25})
    assert resp.status_code == 200, f"创建用户失败: {resp.text[:200]}"
    return resp.json()["data"]


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """终端输出测试结果摘要：通过率快速反馈，无需打开 HTML 报告"""
    total = getattr(terminalreporter, "_numcollected", None) or 0
    passed = len(terminalreporter.stats.get("passed", []))
    failed = len(terminalreporter.stats.get("failed", []))
    errors = len(terminalreporter.stats.get("error", []))
    skipped = len(terminalreporter.stats.get("skipped", []))
    xfailed = len(terminalreporter.stats.get("xfailed", []))
    xpassed = len(terminalreporter.stats.get("xpassed", []))

    pass_rate = (passed / total * 100) if total > 0 else 0.0
    ok = failed == 0 and errors == 0 and xpassed == 0
    outcome = "✅ 全部通过" if ok else "❌ 存在失败"

    terminalreporter.section("测试结果摘要")
    terminalreporter.write_line(f"总用例数  : {total}")
    terminalreporter.write_line(f"通过      : {passed} ✅")
    terminalreporter.write_line(f"失败      : {failed} ❌")
    terminalreporter.write_line(f"错误      : {errors} ⚠️")
    terminalreporter.write_line(f"跳过      : {skipped} ⏭️")
    if xfailed or xpassed:
        terminalreporter.write_line(f"预期失败  : {xfailed} | 意外通过: {xpassed}")
    terminalreporter.write_line(f"通过率    : {pass_rate:.1f}%  {outcome}")
