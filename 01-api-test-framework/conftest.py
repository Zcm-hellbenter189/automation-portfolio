"""pytest 全局夹具：
  - env             --env 参数（dev/test/prod）
  - client          按 --env 配置创建的 HTTP 客户端（session 级，复用连接）
  - unauth_client   未登录客户端（负向鉴权用例用，遵守 --env 配置）
  - auto_login      session 级自动登录 + 准备依赖数据（token / user_id）
  - created_user    每用例独立创建用户（消除用例间隐式顺序耦合）

会话预检（pytest_configure）：
  - 跑用例前先探测接口服务是否可达；不可达就输出一句人话提示并中止，
    而不是让 requests/urllib3 抛出 60+ 行的 ConnectionRefusedError 栈。
"""
import os
import socket
import time
from urllib.parse import urlparse

import pytest

from config.loader import load_config, load_login
from core.extractor import VariablePool, extract_variables
from core.http_client import HttpClient
from utils.logger import get_logger

# 与 client / unauth_client 夹具的兜底默认值保持一致
DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def _probe_service(base_url: str, env: str, timeout: float = 1.5) -> None:
    """探测接口服务是否可达，不可达则抛出可直接看懂的报错

    :param base_url: 本次运行使用的服务地址（来自 config.yaml，可能被 BASE_URL 环境变量覆盖）
    :param env:      当前 --env 值，仅用于提示信息
    :param timeout:  连接超时（秒）；本地 Mock 服务应毫秒级响应，1.5s 足够

    为什么要有这一步：
      服务没启动时，底层会依次抛 ConnectionRefusedError → NewConnectionError
      → MaxRetryError → requests.ConnectionError，几十行栈里真正有用的信息
      （"这个端口没人监听"）埋在最底层。这里提前用 TCP 探测（不经过 HTTP），
      把环境问题在"跑用例之前"一次性说清。

    为什么用 pytest.UsageError 而不是 pytest.exit：
      UsageError 的输出是干净的一行 `ERROR: xxx`；exit 会走 stderr 并带上
      `Exit: ` 前缀，可读性不如前者。
    """
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    # 未显式写端口时按协议取默认端口（http=80 / https=443）
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        # create_connection 只做 TCP 握手，能连上就说明端口有人监听；
        # with 语句保证探测用的 socket 立即关闭，不占用连接
        with socket.create_connection((host, port), timeout=timeout):
            return
    except OSError as e:  # 包含 ConnectionRefusedError / timeout / 域名解析失败
        raise pytest.UsageError(
            f"接口服务不可达：{base_url}（{host}:{port} 连接失败：{e}）\n"
            "这通常是「服务没启动」，不是用例代码的问题。任选一种方式后重试：\n"
            "  1) python run.py                         # 一条龙：起 Mock 服务 → 跑用例 → 关服务\n"
            f"  2) python mock_server.py --port {port}     # 先起服务（终端别关），另开终端跑 pytest\n"
            f"若服务确实在运行：请核对 --env={env} 的 base_url 端口是否与监听端口一致\n"
            "（只做用例收集时可加 --collect-only 跳过本检查，"
            "或设环境变量 SKIP_SERVICE_CHECK=1 关闭）"
        )


def pytest_configure(config):
    """会话开始前的环境预检：服务不可达就直接中止，避免刷屏式异常栈

    跳过场景：
      - --collect-only：只收集不执行，离线干跑（CI 里做用例清单校验）不该被拦；
      - SKIP_SERVICE_CHECK=1：需要临时绕过时的逃生门。
    """
    if config.option.collectonly or os.environ.get("SKIP_SERVICE_CHECK") == "1":
        return
    env = config.getoption("--env")
    _probe_service(load_config(env).get("base_url", DEFAULT_BASE_URL), env)


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
    pool.set("token", token) # 把 token 存入变量池

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
    name = f"夹具用户_{int(time.time()*1000)}"
    resp = client.post("/api/users", json={"name": name, "age": 25})
    logger = get_logger("conftest")
    logger.info(f"前置数据已创建: {resp.json()['data']}") # 输出日志
    assert resp.status_code == 200, f"创建用户失败: {resp.text[:200]}"
    return resp.json()["data"]


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """终端输出测试结果摘要：通过率快速反馈，无需打开 HTML 报告"""
    collected = getattr(terminalreporter, "_numcollected", None) or 0
    passed = len(terminalreporter.stats.get("passed", []))
    failed = len(terminalreporter.stats.get("failed", []))
    errors = len(terminalreporter.stats.get("error", []))
    skipped = len(terminalreporter.stats.get("skipped", []))
    xfailed = len(terminalreporter.stats.get("xfailed", []))
    xpassed = len(terminalreporter.stats.get("xpassed", []))

    # 通过率的分母必须是「实际执行数」，不能用「收集数」：
    # 用 -m "not slow" 过滤时，被跳过的用例若仍计入分母，会出现
    # 「15/16 = 93.8%」却同时显示「✅ 全部通过」的自相矛盾结果。
    executed = passed + failed + errors + skipped + xfailed + xpassed
    # 被 marker 过滤掉的用例数：由「收集数 − 实际执行数」推导，
    # 比依赖 pytest 内部属性（不同版本命名不一）更稳。
    deselected = max(collected - executed, 0)
    pass_rate = (passed / executed * 100) if executed > 0 else 0.0
    ok = failed == 0 and errors == 0 and xpassed == 0
    outcome = "✅ 全部通过" if ok else "❌ 存在失败"

    terminalreporter.section("测试结果摘要")
    terminalreporter.write_line(f"收集用例数: {collected}（其中未选中 {deselected}）")
    terminalreporter.write_line(f"实际执行  : {executed}")
    terminalreporter.write_line(f"通过      : {passed} ✅")
    terminalreporter.write_line(f"失败      : {failed} ❌")
    terminalreporter.write_line(f"错误      : {errors} ⚠️")
    terminalreporter.write_line(f"跳过      : {skipped} ⏭️")
    if xfailed or xpassed:
        terminalreporter.write_line(f"预期失败  : {xfailed} | 意外通过: {xpassed}")
    terminalreporter.write_line(f"通过率    : {pass_rate:.1f}%  {outcome}")
