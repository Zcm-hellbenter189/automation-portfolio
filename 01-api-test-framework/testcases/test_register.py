"""公开注册接口用例：无需登录即可注册"""
import pytest

from config.loader import BASE_DIR
from core import assertions
from utils.data_loader import load_yaml

# 注册用例数据：一条数据 = 一条用例（payload 请求体 + expect 期望结果）
CASES = load_yaml(BASE_DIR / "data" / "cases.yaml")["register_user"]


# 把 CASES 逐条注入测试函数：有几条数据就展开成几条独立用例
@pytest.mark.parametrize("case", CASES, ids=[c.get("name", "未命名用例") for c in CASES])
def test_register_without_token(client, case):
    """未登录（无 Authorization）也能注册成功

    client 未触发 auto_login，所以不带 token——
    能注册成功恰好证明该接口是公开的（对比 POST /api/users 无 token 会返回 401）。
    """
    # 发送注册请求：case["payload"] 作为请求体（此时请求头里没有 Authorization）
    resp = client.post("/api/register", json=case["payload"])
    # 期望结果从该条数据的 expect 读取：成功 200 / 缺 name 400 各自校验
    expect = case["expect"]
    # 第一步：校验 HTTP 状态码是否与期望一致
    assertions.assert_status_code(resp,expect["status_code"])

    # 第二步：只有注册成功(200)才深挖返回内容——业务码 + 必填字段
    if resp.status_code == 200:
        assertions.assert_code(resp, expect["code"])
        assertions.assert_required_fields(resp, ["id", "name", "age"])

