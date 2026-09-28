"""下单接口用例：完整依赖链 登录 → 创建用户 → 下单"""
from core import assertions


def test_place_order_uses_dependency_chain(client, auto_login):
    """依赖链演示：登录取 token → 创建用户取 user_id → 下单

    这是接口自动化的核心难点场景：下游接口依赖上游接口的返回值。
    auto_login 夹具通过变量池把 token / user_id 自动传递到本用例。
    """
    user_id = auto_login.get("user_id")
    assert user_id is not None, "前置数据缺失：auto_login 未能提供 user_id"
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


def test_place_order_without_token(unauth_client):
    """未登录下单应返回 401（用独立 client 验证，避免 token 干扰）"""
    resp = unauth_client.post("/api/orders", json={"user_id": 1, "product": "x", "amount": 1})
    assertions.assert_status_code(resp, 401)


def test_keepalive_body_not_polluted(unauth_client):
    """回归：鉴权失败且带 body 的 POST，不应污染同一条连接上的下一条请求

    【这个用例在守什么】
    HTTP/1.1 默认 keep-alive，一条 TCP 连接会连续承载多个请求。服务端**必须**把每个
    请求的 body 消费到 Content-Length 边界，rfile 读指针才会停在下一条请求的起点。
    若某个分支（典型：鉴权失败提前 return）没读 body，残留字节就会被下一条请求当成
    请求行 → 标准库抛 400 `Bad request syntax ('{...}GET /api/users HTTP/1.1')`。

    【为什么必须用同一个 client】
    只有复用同一条连接才可能复现。这里用的 unauth_client 是 **session 级**夹具，
    多次调用共享连接 —— 这正是当初那个缺陷的触发条件。

    【为什么还要单独写一条（关键）】
    当时的 18 条用例**确实**抓到了这个缺陷，但靠的是巧合，同时依赖四个偶然条件：
      ① unauth_client 是 session 级（共用连接）
      ② test_order.py 按文件名字典序先于 test_user.py 执行
      ③ test_place_order_without_token 恰好存在（由它制造残留）
      ④ 用例串行执行
    任一条件被改动（改夹具作用域 / 改文件名 / 删用例 / 加 -n 并行），缺陷就会重新隐形。
    本用例把「先 POST 带 body、再 GET」写进**同一个函数内** —— 自己制造残留、自己验证，
    不依赖任何执行顺序，把"偶然覆盖"变成"必然守住"。

    【变异自检】（验证它真的在守门）
    把 mock_server.py 中 do_POST 首行的 self._consume_body() 注释掉 → 本用例应变红；
    恢复后应变绿。若注释掉仍是绿的，说明这条用例没有抓到点子上。
    """
    # ① 制造"带 body 且会提前 return"的请求：未登录 → 401（鉴权分支不会读业务参数）
    resp_post = unauth_client.post(
        "/api/orders",
        json={"user_id": 1, "product": "x", "amount": 1},
    )
    assertions.assert_status_code(resp_post, 401)

    # ② 同一条连接上的下一条请求：必须是业务 401，而不是标准库抛出的 400
    resp_get = unauth_client.get("/api/users")
    assertions.assert_status_code(resp_get, 401)

