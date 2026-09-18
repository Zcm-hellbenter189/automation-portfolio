"""公开注册接口用例：无需登录即可注册"""
import threading
import time

import pytest

from config.loader import BASE_DIR
from core import assertions
from core.http_client import HttpClient
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
    # 浅拷贝：case["payload"] 是 CASES 里原始 dict 的引用，
    # 直接改它会把改动落到"模块级共享数据"上（下面详述）
    payload=dict(case["payload"])
    # 需要唯一化的数据在这里拼后缀：
    # mock 数据活在进程内存里，固定名第二次运行会撞上重名检查（1006）
    if case.get("unique_name"):
        payload["name"]=f"{payload['name']}_{int(time.time()*1000)}"

    # 发送注册请求：用拼好后缀的 payload 作为请求体（此时请求头里没有 Authorization）
    resp = client.post("/api/register", json=payload)
    # 期望结果从该条数据的 expect 读取：成功 200 / 缺 name 400 各自校验
    expect = case["expect"]
    # 第一步：校验 HTTP 状态码是否与期望一致
    assertions.assert_status_code(resp,expect["status_code"])

    # 第二步：只有注册成功(200)才深挖返回内容——业务码 + 必填字段
    if resp.status_code == 200:
        assertions.assert_code(resp, expect["code"])
        assertions.assert_required_fields(resp, ["id", "name", "age"])

@pytest.mark.parametrize("workers", [pytest.param(8, id=f"并发8线程-恰好1个成功200其余400")])
def test_register_concurrent_same_name(client,auto_login,workers):
    """并发同名注册：恰好 1 个成功，其余全部 1006，且库里只有 1 条

       这是"判重与写入在同一临界区"的证据：若判重退回锁外，
       这里会稳定出现多个 200（把 bug 复现出来）。
       """
    # 起线程之前生成一次 → 8 个线程共享同一个 name（竞态的前提）
    name = f"并发用户_{int(time.time() * 1000)}"
    barrier = threading.Barrier(workers, timeout=10) # 起跑线：到齐才放行
    results=[]  # 收集结果（list.append 在 GIL 下是原子的，无需加锁）
    errors = [] # 收集线程内异常，否则线程静默死亡用例照样绿
    def register_once():
        # 每线程独立客户端：requests.Session 不保证线程安全，
        # 共用会把"服务端竞态"和"客户端排队串行发出"混在一起（违反单一变量原则）
        http = HttpClient(base_url=client.base_url, timeout=10)
        try:
            barrier.wait() # 先集合
            resp = http.post("/api/register", json={"name": name, "age": 18})
            results.append((resp.status_code,resp.json().get("code"))) # ← 显式收集
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=register_once) for _ in range(workers)]
    for t in threads:
        t.start() #start() 是"提交完就返回 for循环瞬间就跑完,8个线程差不多同时被唤醒
    for t in threads:
        t.join()  #join() 是"建立同步点"：它保证主线程看到的是全部线程都干完活之后的世界

    # ① 先确认全部线程都正常跑完，否则下面的统计会失真
    assert not errors, f"线程内出现异常: {errors}"
    assert len(results) == workers, f"应有 {workers} 个响应，实际 {len(results)} 个"

    # ② 响应分布：恰好 1 个成功，其余全部 1006
    ok = [r for r in results if r == (200, 0)]
    dup = [r for r in results if r == (400, 1006)]
    assert len(ok) == 1, f"应恰好 1 个注册成功，实际 {len(ok)} 个；全部结果={results}"
    assert len(dup) == workers - 1, f"其余应全部 1006，实际 {len(dup)} 个；全部结果={results}"

    # ③ 数据事实：库里同名用户只能有 1 条
    # 响应是"服务端的说法"，库才是"事实"——只断响应会漏掉"回了 1006 但照样写入"
    listed=client.get(f"/api/users") #「需登录，靠 auto_login 注入 token」
    assertions.assert_status_code(listed,200)
    matched =[u["name"] for u in listed.json()["data"] if u["name"] == name]
    assert len(matched )==1,f"同名记录应只有1条，实际{len(matched )}条"


