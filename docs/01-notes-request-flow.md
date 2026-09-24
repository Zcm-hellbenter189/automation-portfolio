# 笔记：一次接口请求是怎么跑起来的

> 记录一次 `client.post(...)` 从用例到响应的完整链路、两套触发机制、HTTP 协议的归属，
> 以及由此推出的实战结论。配合 `docs/code-guide-01-api-test-framework.md` 一起看。

---第 N 关完成
① 目录树：...
② pytest 输出：...（几条通过）
③ 三行总结：这关我学会了 / 踩了什么坑 / 还存疑的地方

## 一、完整链路（从用例到响应）

```
① 用例:      client.post("/api/register", json={"name": "王五"})
                    ↓ 显式调用
② 框架:      HttpClient.post → HttpClient.request
              （合并 headers、设默认超时、写日志、准备重试）
                    ↓ 显式调用
③ requests:  self.session.request(method, url, **kwargs)   ← 第三方库方法
                    ↓
④ requests 内部: Session.send → HTTPAdapter.send → urllib3 → http.client → socket
                    ↓ 把请求按 HTTP 报文格式写成字节流
⑤ 网络:      POST /api/register HTTP/1.1 / Host / Content-Length / 空行 / body
══════════════════ TCP 传输 ══════════════════
⑥ 服务器:    ThreadingHTTPServer 收到连接 → 每个请求 new 一个 MockHandler 实例
                    ↓
⑦ 父类:      BaseHTTPRequestHandler.handle_one_request()
              解析请求行 → self.command="POST"、self.path="/api/register"
              解析请求头 → self.headers
              按约定拼名字 → getattr(self, "do_POST")()   ← 自动调用！
                    ↓
⑧ 你的代码:  do_POST() 按 self.path 分发 → _handle_register()
              _read_json() 按 Content-Length 读 body
              业务校验 → 加锁分配 id → 写 users 表
                    ↓
⑨ 响应:      _send() → send_response(状态行) / send_header(头) / end_headers(空行) / wfile.write(body)
                    ↓ 字节流回到客户端
⑩ 客户端:    requests 解析响应 → 生成 Response 对象 → 赋给 resp
              → 用例断言 resp.status_code / resp.json()
```

---

## 二、两套"触发机制"（最容易混）

| 机制 | 例子 | 名字重要吗 |
|---|---|---|
| **显式调用** | `client.post()`、`session.request()`、`_send()` | ❌ 随便起名，靠你自己写调用 |
| **命名约定（钩子/回调）** | `do_POST` / `do_GET`、`pytest_addoption`、`pytest_terminal_summary`、`test_*`、fixture 同名注入 | ✅ **名字必须完全正确**，框架按名反射调用 |

> 结论：`do_POST` 在项目里"找不到调用者"是正常的——调用它的是标准库按 `"do_" + 方法名` 拼出来的。

---

## 三、HTTP 协议是谁写的

| 层次 | 内容 | 谁写的 |
|---|---|---|
| 协议规范 | 请求行 / 头 / 空行 / 正文的格式规则 | IETF 的 RFC 文档（不是代码） |
| 协议实现 | requests（客户端）、http.server（服务端） | 库的作者 |
| 使用协议 | `json=` 一行；`_send` 里组装响应 | **你**（只填内容，格式由库保证） |

- 客户端：`POST /api/... HTTP/1.1`、`Content-Length` 全由 requests 生成；
- 服务端：请求解析全由库完成；`_send` 里你只提供"状态码 + 头 + body"，格式由库方法保证；
- 双方唯一的约定是 **HTTP 报文格式**（不是共享方法名），所以换成 curl / 真实后端都能互通。

---

## 四、由此推出的 5 个实战结论

1. **跨请求状态必须放类属性**：`ThreadingHTTPServer` 每个请求都 new 一个新 handler 实例，实例属性用完即废。
2. **改类属性必须写 `类名.attr += 1`**：`self.attr += 1` 等价于 `self.attr = self.attr + 1`，会**新建实例属性、遮蔽类属性** → 每个请求都从初始值开始（"id 全是 1"的根因）。
3. **body 不会自动读**：父类只解析请求行和头，正文要自己按 `Content-Length` 从 `rfile` 读。
4. **`self.path` 含查询串**：请求 `/api/users?page=1` 时，`== "/api/users"` 会匹配失败。
5. **未实现的 `do_XXX` 会返回 501**：比如 PUT 请求 → 找 `do_PUT` → 没有 → `501 Unsupported method`。

---

## 五、标准库 vs 第三方库（本项目用到的）

| 类型 | 本项目用到的 |
|---|---|
| 标准库（Python 自带） | `http.server`、`json`、`threading`、`socket`、`subprocess`、`argparse`、`time`、`pathlib`、`logging`、`functools` |
| 第三方（需 pip 安装） | `requests`、`pytest`、`pytest-html`、`PyYAML` |

---

## 六、两个语法点巩固

```python
# 1. 嵌套 dict 取值：只能取"当前这一层"的 key
case = {"name": "...", "payload": {...}, "expect": {"status_code": 200, "code": 0}}
case["status_code"]                  # ❌ KeyError：顶层没有这个 key
case["expect"]["status_code"]        # ✅ 先取 expect，再往下一层
expect = case["expect"]              # ✅ 更推荐：抽出来复用

# 2. assert 语句：条件为假就抛 AssertionError
assert not missing, f"缺少字段: {missing}"
# 空列表是"假"：bool([]) == False，所以 not [] == True → 通过
```

---

## 七、可以写进简历 / 面试的一句话

> 我用 `requests` 封装了测试客户端，用标准库 `http.server` 自建 mock 服务；
> 两者之间只靠 HTTP 协议对接，因此框架与 mock 完全解耦——
> 把 mock 换成真实后端时，用例代码零改动。

