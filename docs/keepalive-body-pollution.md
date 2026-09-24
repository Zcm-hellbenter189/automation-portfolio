# HTTP/1.1 长连接下的「请求体残留」——一次协议升级引发的连锁故障

> **背景**：本项目把 `BaseHTTPRequestHandler.protocol_version` 从默认的 `HTTP/1.0` 改为 `HTTP/1.1`（为启用连接复用、减轻 accept 队列压力）。
> **这个改动打开了长连接，随即暴露出两个此前被"短连接"完全掩盖的缺陷。**
>
> 结论先行：**改协议默认值不是"改一个参数"，而是推翻了一批隐含假设** —— 必须做全量回归。

---

## 一、现象

修复前跑 `python run.py`：

```
...........F......
FAILED testcases/test_user.py::test_users_require_auth
AssertionError: HTTP 状态码不符: 实际 400，期望 401
响应体: <!DOCTYPE HTML> ... <p>Message: Bad request syntax
        ('{"user_id": 1, "product": "x", "amount": 1}GET /api/users HTTP/1.1')</p>
```

**两条关键线索**：

1. **400 的响应体是标准库的 HTML 错误页**，不是我们的业务 JSON
   → 说明这个 400 由 `http.server` 自己抛出，**请求根本没进我们的 handler**。
2. **错误消息里两段内容拼在一起**：`{...JSON...}` + `GET /api/users HTTP/1.1`
   → 服务端把「**上一条请求的 body**」当成了「**这一条请求的请求行**」的一部分。

---

## 二、根因一：请求体没被消费 → 残留污染下一条请求

HTTP/1.1 的一条 TCP 连接上连续承载多个请求，服务端**必须把当前请求的消息体消费到 `Content-Length` 指定的边界**，`rfile` 的读指针才会停在下一条请求的起始位置。

而本项目大量采用「**鉴权失败就提前 return**」的写法，且 `_read_json()` 写在鉴权**之后**：

```python
def _handle_create_order(self):
    if not self._is_authed():
        self._send(401, ...)
        return                  # ← 提前返回，body 一个字节都没读
    body = self._read_json()    # ← 只有鉴权通过才会读
```

**于是**：

```
test_place_order_without_token（unauth_client 发 POST /api/orders，带 body）
  → 鉴权失败 → 401 → 提前 return → body 未被读走，残留在 socket 缓冲
  → HTTP/1.1 keep-alive：连接保持
  → test_users_require_auth（同一个 unauth_client = 同一条连接）发 GET /api/users
  → 服务端读"请求行"，读到的却是 "{...}GET /api/users HTTP/1.1"
  → parse_request 失败 → 标准库 400 Bad request syntax
```

**为什么偏偏是 `test_users_require_auth` 失败**：`unauth_client` 是 **session 级 fixture**，被
`test_order.py::test_place_order_without_token`（先跑）和 `test_user.py::test_users_require_auth`（后跑）**共用同一条连接**。
pytest 按文件名字典序执行（`test_order.py` < `test_user.py`），恰好保证"**制造残留**"总在"**踩到残留**"之前。

> ⚠️ 这个失败**依赖执行顺序**。单独跑 `test_users_require_auth` 永远是绿的 —— 典型的**顺序耦合**。

**为什么以前没暴露**：HTTP/1.0 每个响应后**关闭连接**，残留 body 随连接一起销毁。

> **"以前没出问题" ≠ "以前是对的"，只是缺陷被短连接掩盖了。**

---

## 三、根因二：handler 实例被复用 → 请求级缓存跨请求泄漏

**第一版修复**（方向对，但引入新问题）：在分发入口无条件消费 body（`do_POST` / `do_GET` / `do_PUT` 开头调 `_consume_body()`），并让 `_read_json()` **带缓存**（因为 rfile 是流，读一次就消耗掉，handler 里还要用同一份数据）。

**结果测试反而更差**（1 失败 → 2 失败 + 9 错误，连登录都挂）：

```
POST /api/login → 400 {"code": 1002, "msg": "缺少参数: username/password"}
```

**根因**：`socketserver` 的 `BaseRequestHandler.handle()` 是**循环**结构 ——

```python
def handle(self):
    self.handle_one_request()
    while not self.close_connection:
        self.handle_one_request()
```

> **同一个 handler 实例会服务同一条连接上的所有请求**，而不是「每个请求一个新实例」。

于是 `_body_cache` 作为**实例属性**，在第二个请求时还留着**第一个请求的 body** → 缓存被判定为"已读过" → **新请求的 body 根本没被读走**（残留继续污染），而 handler 拿到的却是**上一条请求的数据**（所以登录会说"缺少参数"）。

**⚠️ 为什么这个假设此前从未被挑战**：HTTP/1.0 时每个响应后连接关闭 → `while` 循环只跑一次 → 实例确实只服务一个请求，"每请求一实例"的错觉成立。
**改成 HTTP/1.1 后，实例生命周期从「一个请求」变成「整条连接」。**

**修复**：在每个请求开始时重置缓存 ——

```python
def handle_one_request(self):
    self._body_cache = None   # None = 本次请求的 body 尚未读取
    super().handle_one_request()
```

### 补充：`_body_cache` 是什么？凭什么能"跨方法"使用？

```python
self._body_cache = None                        # 写在 handle_one_request 里
cached = getattr(self, "_body_cache", None)    # 写在 _read_json 里
```

**两个不同的方法，为什么能访问"同一个变量"？—— 因为 `self` 是同一个实例。**

`self._body_cache = xxx` **不是局部变量**，它把值存到了**实例身上**：

```python
self._body_cache = {}          # 等价于
self.__dict__["_body_cache"] = {}
```

**`self` 本质上就是一张字典**，`self.xxx = yyy` 就是往这张字典里存一个键值对。

```python
h = MockHandler(...)       # 一个实例（同一条连接的多个请求共用它）
h.handle_one_request()     # self = h → h.__dict__["_body_cache"] = None
h._read_json()             # self = h → 读到 h.__dict__["_body_cache"] ✅
```

**⇒ 能跨方法，靠的是「同一个实例」。反过来说：实例活多久，这个数据就活多久。**

> ⚠️ **这正是上一节 bug 的根因** —— `socketserver` 的实例活了**一整条连接**，所以缓存也活了一整条连接。
> **不是"缓存写错了"，而是"生命周期没对齐"。**

#### 那行赋值到底做了什么？—— `self.xxx = v` 是"给实例动态加属性"

```python
self._body_cache = None
# 等价于
self.__dict__["_body_cache"] = None
```

**Python 的实例属性是动态的**：不需要提前声明，**赋值即创建**（不像 Java / C++ 要先在类里声明字段）：

```python
class A:
    pass

a = A()
a.x = 1                  # ✅ 直接就能加，A 里从没写过 x
print(a.__dict__)        # {'x': 1}
```

#### 补充：**所有**实例都自带字典吗？—— 默认是，但有两个例外

**① 默认情况：有**

**实例字典存"实例属性"，类字典存"类属性 + 方法"** —— 是**两个不同的字典**：

```python
class A:
    class_var = 1

a = A()
a.own = 2
print(a.__dict__)                  # {'own': 2}        ← 只有实例属性
print("class_var" in a.__dict__)   # False ✅ 类属性**不在**实例字典里（靠查找链才能拿到）
```

**② 例外一：定义了 `__slots__` 的类**

```python
class B:
    __slots__ = ("x", "y")

b = B()
b.x = 1                  # ✅ 只能赋 slots 里声明过的
b.z = 2                  # ❌ AttributeError（连拼错属性名都会被抓出来）
b.__dict__               # ❌ AttributeError: 'B' object has no attribute '__dict__'
```

**用途**：**省内存**（每个实例少一张哈希表，空 dict 也要 60+ 字节）、**属性访问更快**、**字段固定**、**拼错报错**。适合需要创建几十万个实例的场景。

> ⚠️ **本项目用不了 `__slots__`**：`BaseHTTPRequestHandler` 依赖大量**运行时动态属性**（`self.request` / `self.rfile` / `self.wfile` / `self.headers` / `self.path` / `self.close_connection` …），一旦限制字段就会崩。
> 这也再次说明：**`_body_cache` 只能走"动态创建 + `getattr` 兜底"这条路。**

**③ 例外二：内置类型的实例没有 `__dict__`**

```python
(1).__dict__        # ❌ AttributeError: 'int' object has no attribute '__dict__'
"abc".__dict__      # ❌
[].__dict__         # ❌

"abc".foo = 1               # ❌ 字符串不能加属性
class MyStr(str): pass
MyStr("abc").foo = 1        # ✅ 子类实例有 dict
```

**原因**：内置类型是 C 实现的，为省内存采用**固定布局**，不挂字典。

**④ 怎么查**

```python
hasattr(obj, "__dict__")     # 有没有
vars(obj)                    # ≡ obj.__dict__（没有则 TypeError）
type(obj).__dict__           # ⚠️ 这是**类**的字典，不是实例的
```

**⑤ 属性查找链：读走链条，写只写实例**

```
读 obj.x：
  1. 类（及 MRO）里的「数据描述符」（如 property）
  2. obj.__dict__["x"]              ← 实例字典
  3. 类（及 MRO）里的普通属性 / 方法  ← 类字典
  4. __getattr__（若定义）→ 否则 AttributeError

写 obj.x = v：
  → 直接写 obj.__dict__["x"]（除非 x 是数据描述符）
```

> **这正好解释了你项目里的两种写法**：
> - `self._body_cache = None` → **写**：进**实例字典** ✅
> - `self.users[uid] = user` → 先**读**到类属性 `users`（走第 3 步），再**原地修改那个 dict** ✅

#### 小结：`self` 到底是什么？它的值会变吗？

**`self` = 调用这个方法的那个实例**，由 Python **自动**传入：

```python
a.m()        # Python 实际执行的是 A.m(a)  ← 把 a 作为第一个参数塞进去
```

**它不是关键字，只是个约定俗成的参数名**（写 `this` 语法上也合法，但没人这么干 → 违反 PEP 8）。

**在本项目里，`self` 的值"按连接变"，不是"每次调用都变"**：

| 场景 | `self` 是否相同 |
|---|---|
| **同一条连接**上的多个请求 | **相同** ✅ ← 所以请求级状态会泄漏（昨天那个 bug 的根源） |
| **不同连接**的请求 | **不同** ✅ ← 所以连接之间天然隔离 |

> **你昨天打印的那个 `id(self)`，就是"self 的身份"** —— 它一直不变，正说明 `self` 始终是同一个实例。

**⚠️ 关键：`self` 是"查找的起点"，不是"私有的容器"**

`self.xxx` 最终找到什么，取决于**属性查找链**：

```python
self.users[uid] = user        # 沿链条找到【类属性】users —— 所有实例共享
self._body_cache = None       # 直接写【实例属性】—— 只有自己可见
```

**同一个 `self`，两种完全不同的效果** —— 区别只在于"这个属性是在类上还是在实例上"。

**为什么 `socketserver` 不设计成"每请求一个新实例"？**

- 创建对象有开销，长连接下"每请求 new 一个"不划算；
- "**一个 handler 负责一条连接**"语义上更自然，还能在实例上存**连接级**状态（如协商的协议版本、连接建立时间）。

**代价就是**：它很容易被误用成"请求级状态"的容器 —— 所以必须靠**在 `handle_one_request` 里显式重置**来纠正。

> **一句话**：`self` 的生命周期 = **实例**的生命周期 = **连接**的生命周期。
> **任何"只该活一个请求"的状态，都必须自己动手重置。**

**三种方法的首参数对照**（本项目主要用第一种）：

| 类型 | 第一个参数 | 自动传入 | 调用 |
|---|---|---|---|
| **实例方法** | `self` | **实例** | `a.m()` |
| `@classmethod` | `cls` | **类本身** | `A.m()` / `a.m()` |
| `@staticmethod` | 无 | 不传 | `A.m()` / `a.m()` |

⚠️ 少写 `self` 的典型报错：`TypeError: m() takes 0 positional arguments but 1 was given` —— "多出来的那个"就是 Python 自动传的 `self`。

**"新增"还是"覆盖"？看之前有没有**：

| 情况 | 行为 |
|---|---|
| 实例上**没有**、类上也没有 | **新增**实例属性 |
| 实例上**已有** | **覆盖**它的值 |
| **类上有**（类属性）、实例上没有 | **新增**实例属性，并**遮蔽**类属性 |

**所以 `handle_one_request` 里的这一行，在不同时刻承担两个作用**：

| 时刻 | 作用 |
|---|---|
| 连接的**第 1 个请求** | **创建**这个属性（此前它根本不存在） |
| 后续每个请求 | **重置**它（防止跨请求泄漏） |

**⚠️ 动态属性的代价：属性名拼错不会报错**

```python
self._body_cahce = None                                 # ← 拼错了（cahce）
cached = getattr(self, "_body_cache", None)             # → 永远 None → 每次都重新读 rfile ❌
```

**赋值时不报错，只在行为上静默出错** —— 这是动态语言相对 Java / C++（有编译期字段检查）的典型风险。

**防法**：① PyCharm 对"未解析的属性引用"会给波浪线提示；② 关键属性在 `__init__` 里写一遍当"声明"；③ 靠测试断言行为，而不是只读代码。

> **本项目这条属性有个额外风险**：它**不能**写进类体（否则变成类属性被所有实例共享），只能靠 `getattr` 兜底 ——
> 且 `getattr(self, "_body_cache", None)` 里的 `"_body_cache"` 是**字符串字面量**，**IDE 的"重命名"重构改不到它** ⚠️
> ⇒ **改这个属性名时必须改两处**：`handle_one_request` 里的赋值 + `_read_json` 里的 `getattr` 字符串。

**四种"变量"的对照**（本项目四种都有，各司其职）：

| 类型 | 写法 | 存在哪 | 生命周期 | 访问范围 |
|---|---|---|---|---|
| **局部变量** | `body = ...` | 方法栈 | 方法执行期间 | 只有本方法 |
| **实例属性** | `self._body_cache` | `instance.__dict__` | **实例的整个生命周期** | 该实例的所有方法 |
| **类属性** | `self.users` / `MockHandler.users` | `Class.__dict__` | 进程存活期间 | **所有实例** |
| 模块全局 | `TOKEN_PREFIX` | 模块 `__dict__` | 模块加载后常驻 | 整个模块 |

- `users` / `_lock` / `next_user_id` **必须**是类属性 → 多个请求要共享同一份数据 ✅
- `_body_cache` **必须**是实例属性 → 只服务本次请求，不该跨请求共享 ✅

**⚠️ 一个极易踩的 Python 陷阱：`self.x = v` 和 `self.x[k] = v` 效果完全不同**

```python
self._body_cache = None        # 整体赋值 → 创建 / 覆盖**实例属性**
self.users[uid] = user         # 下标赋值 → **原地修改类属性那个 dict**
```

- **整体赋值**（`=`）→ 属性挂到**实例**上（类上若有同名属性，实例属性会**遮蔽**它）
- **下标赋值**（`[...] =`）→ 并没有给 `self.users` 赋值，只是修改它**指向的那个对象**；而 `self.users` 查到的是**类属性** → **改的就是类属性**

**本项目两种都用对了**（原注释已标出这一点 ✅）：

```python
self.users[uid] = user  # 原地修改类级共享的 users 表（不是重新赋值）
```

> 若把 `_body_cache` 写成**类属性**（`_body_cache = None` 写在类体里），就是灾难：**所有请求共用一份缓存** —— 等于"每个请求都读到别人的 body"。

### ❓ `cached = getattr(self, "_body_cache", None)` 是什么？

`getattr(对象, "属性名", 默认值)` 是内置函数，作用是**安全地读属性**：

```python
cached = getattr(self, "_body_cache", None)
# 完全等价于
try:
    cached = self._body_cache
except AttributeError:
    cached = None
```

**为什么不能直接写 `self._body_cache`**：**第一次调用时这个属性还不存在**（类里没定义、`__init__` 里也没设）→ 直接访问会抛 `AttributeError: 'MockHandler' object has no attribute '_body_cache'`。

**为什么不在类里给它一个默认值**：见上一节 —— 那会变成**类属性**，所有实例共享，比"跨请求泄漏"更糟 ❌

**也不适合放在 `__init__` 里初始化**：

```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)   # ⚠️ 这一行内部就已经开始处理请求了！
    self._body_cache = None             # 来不及
```

> ⚠️ `socketserver.BaseRequestHandler.__init__` 会**直接调用 `handle()`** —— "`__init__` 还没返回，请求已经被处理完了"。
> 所以"在 `__init__` 里初始化请求级状态"这条路，在 `http.server` 里根本走不通。
> ⇒ **`getattr` 兜底 + `handle_one_request` 重置，是最简洁可靠的组合。**

**⚠️ 判断方式：必须用 `is not None`，不能用真值判断**

```python
cached = getattr(self, "_body_cache", None)
if cached is not None:      # ✅ 正确
    return cached
```

因为**合法的缓存值可能是 `{}`**（无请求体），而 `{}` 是 falsy：

```python
if cached:                  # ❌ {} 会走 else → 再去读 rfile（已空）→ 拿到空数据
    return cached
```

> 这和前面「`if age:` 会把合法的 `age=0` 误判为"没传"」**是同一个坑**：
> **判断"有没有"用 `is None`；判断"空不空"才用真值。**

**顺带**：`getattr` 的另一个常见用途是**动态属性名**（属性名来自变量）：

```python
field = "name"
getattr(obj, field)         # 等价于 obj.name
```

数据驱动测试里常用（从 YAML 读字段名再动态取值）。这里 `"_body_cache"` 是写死的字符串，用的是它的**默认值兜底**能力。

### ❓ `handle_one_request` 什么时候执行？

**完整调用链**（从 TCP 连接到业务 handler）：

```
客户端发起 TCP 连接
  ↓
ThreadingHTTPServer 接受连接 → 为该连接开一个线程
  ↓
线程里创建 handler 实例：MockHandler(request, client_address, server)
  ↓
socketserver.BaseRequestHandler.__init__ 内部：
      self.setup()
      try:
          self.handle()          # ← 注意：__init__ 里就调用了 handle()
      finally:
          self.finish()
  ↓
MockHandler.handle()（继承自 BaseHTTPRequestHandler）
      self.close_connection = True
      self.handle_one_request()              # ← 第 1 个请求
      while not self.close_connection:
          self.handle_one_request()          # ← 第 2、3、4… 个请求（同一条连接）
  ↓
BaseHTTPRequestHandler.handle_one_request()  ← **我们重写的就是这一层**
      - 读请求行、解析请求头（parse_request）
      - 反射调用 do_GET / do_POST / do_PUT
  ↓
do_POST() → _handle_xxx()
```

**执行次数对照**：

| | handler **实例**创建 | `handle_one_request` 执行 |
|---|---|---|
| HTTP/1.0 | 每条连接 **1 次** | 每条连接 **1 次**（响应后即关连接） |
| HTTP/1.1 | 每条连接 **1 次** | 每条连接 **N 次**（N = 该连接上跑过的请求数） |

> **实例只创建一次，方法却要跑 N 次** —— 这正是"实例属性跨请求泄漏"的根源。

**循环要不要继续由谁决定**：`self.close_connection`。请求头带 `Connection: close`、或响应里声明关闭，都会让它变成 `True`。

#### ⚠️ 重写这个方法后，父类原来的逻辑还会执行吗？——**会，因为我写了 `super()`**

```python
def handle_one_request(self):
    self._body_cache = None           # ① 先做自己的事
    super().handle_one_request()      # ② 再显式调用父类原来的实现
```

**Python 的规则**：**子类重写（override）后，父类的实现不会自动执行** —— 必须自己显式调用 `super().xxx()`。

```
self.handle_one_request()          ← 调的是你的版本（属性查找先找到子类）
  ↓
self._body_cache = None            ← 你的代码
  ↓
super().handle_one_request()       ← 显式跳到父类版本
  ↓
BaseHTTPRequestHandler.handle_one_request()
      - 读请求行、解析请求头（parse_request）
      - 反射调用 do_POST
```

**如果忘了写 `super()`**：

```python
def handle_one_request(self):
    self._body_cache = None
    # 忘了 super() → 父类实现完全不执行
```

→ **不读请求行、不解析头、不调 `do_POST`** → 请求永远得不到响应，客户端一直等到超时 💥

**`super()` 是什么**：`super().handle_one_request()` 等价于 `BaseHTTPRequestHandler.handle_one_request(self)` —— 按 **MRO**（方法解析顺序）找"下一个类"的同名方法。单继承下就是父类；多继承时它会沿 MRO 链正确前进（这正是 `super()` 优于硬写父类名的地方）。

**两种意图要分清**：

| 意图 | 写法 | 效果 |
|---|---|---|
| **完全替换**父类行为 | 只写自己的代码 | 父类逻辑**不执行** |
| **扩展**父类行为（加一层） | 调用 `super()` | 父类逻辑**照常执行**，你在前后插代码 |

**我们要的是"扩展"** —— 在原有请求处理流程**前面**插一步重置。

**⚠️ 两行代码的顺序也很关键**：

```python
# ✅ 正确：先重置 → 再处理（处理时缓存是干净的）
def handle_one_request(self):
    self._body_cache = None
    super().handle_one_request()

# ❌ 错误：先处理 → 再重置（处理时缓存是上一条请求的 → 白改）
def handle_one_request(self):
    super().handle_one_request()
    self._body_cache = None
```

第二种会**原样重现**那个 bug：`super()` 内部会调 `do_POST` → handler 读 `_read_json()` → 此刻 `_body_cache` 还是**上一条请求的值** → 读到旧数据。

#### 自己验证（完整操作步骤）

**① 加一行临时日志**

```python
def handle_one_request(self):
    self._body_cache = None
    print(f"[mock] 新请求开始 | handler 实例 id={id(self)}")   # 临时调试用，验证完删掉
    super().handle_one_request()
```

**② 新开一个终端，前台起服务**（要盯着这个终端的输出）

```bat
cd 01-api-test-framework
python mock_server.py --port 8000
```

> ⚠️ 改了代码**必须重启服务**（Python 不热重载）。若 8000 已被占用，先 Ctrl+C 停掉旧进程，或换 `--port 8001`。

**③ 再开一个终端，用 `Session` 连发 3 个请求（复用连接）**

```bat
..\.venv\Scripts\python.exe -c "import requests; s=requests.Session(); [print(s.get('http://127.0.0.1:8000/api/users').status_code) for _ in range(3)]"
```

**预期**（服务端终端）：

```
[mock] 新请求开始 | handler 实例 id=2437891234560
[mock] 新请求开始 | handler 实例 id=2437891234560      ← 同一个 id！
[mock] 新请求开始 | handler 实例 id=2437891234560      ← 还是同一个！
```

**3 行日志、同一个 id** ⇒ **一个实例服务了 3 个请求** ✅ —— 这就是"实例复用"的直接证据。

**④ 对照组：用裸 `requests` 再发 3 次（不复用连接）**

```bat
..\.venv\Scripts\python.exe -c "import requests; [print(requests.get('http://127.0.0.1:8000/api/users').status_code) for _ in range(3)]"
```

**预期**：**3 行日志、3 个不同的 id** ⇒ 每个请求新建连接 → 新建实例 ✅

> **这一组对照一次性验证了两件事**：
> ① `Session` 会复用连接（同实例）；② 裸 `requests` 不复用（每次新实例）。
> 这也是"为什么客户端要用 `Session`"最直观的证据。

**⚠️ 验证时的坑：`run.py` 会在"端口被占用"时自动改端口**

```
[!] 端口 8000 已被占用，自动改用端口 8001
[*] Mock 服务已启动: http://127.0.0.1:8001
```

**含义**：`run.py` 发现 8000 上已经有服务（你手动起的那个），于是**另起一个 8001 的服务**来跑测试。

**这是容错设计，但也是双刃剑**：

| 好处 | 风险 |
|---|---|
| 测试不会被"端口占用"卡住 | **容易误以为"测的就是那个端口上的服务"** |

**⚠️ 危险场景**：

1. 你改了代码，但**忘了重启 8000 上的服务**（它跑的还是旧代码）；
2. 跑 `pytest`（配置指向 8000）→ **实际测的是旧代码** → 结论完全错。

**本次没踩坑**：`run.py` 起的是 8001 上的**新服务**，加载了最新代码 ✅

**建议习惯**：

- **验证代码改动前，先确认"我要测的那个服务跑的是不是新代码"**；
- 手动起的调试服务，**用完就 Ctrl+C 停掉** —— 别让它长期占着端口干扰后续运行。

**💡 更好的调试输出：打印「客户端源端口」而不是 `id(self)`**

```python
def handle_one_request(self):
    self._body_cache = None
    # 临时调试：实例内存地址 + 客户端源端口
    print(f"[mock] 新请求 | 实例={id(self)} | 客户端源端口={self.client_address[1]}")
    super().handle_one_request()
```

**为什么源端口更直观**：

| 观察 | 含义 |
|---|---|
| **源端口相同** | **同一条 TCP 连接**（连接被复用）✅ |
| **源端口不同** | **不同的 TCP 连接**（每次新建）✅ |

```
裸 requests（3 次）→ 3 个不同端口
  端口 51501 / 51507 / 51512        ← 每次新连接

Session（3 次）→ 同一个端口
  端口 51520 / 51520 / 51520        ← 复用同一条连接
```

（Windows 的临时端口通常**递增分配**，所以新连接的端口号看起来是连续往上的。）

**⚠️ 另外：服务端日志会「交错」，别被顺序误导**

`ThreadingHTTPServer` 是**每个连接一个线程** → 多个连接同时处理时日志行会交叉：

```
A: 新请求
B: 新请求        ← 插进来了
A: 401
B: 401
```

**判断依据是"配对"（一次「新请求」配一次响应），而不是行的先后顺序。** 手动复制终端输出时也容易漏行 —— **数量对不上时先怀疑日志不全，别怀疑代码**。

**附：`self.client_address` 是什么类型？**

```python
print(type(self.client_address))     # <class 'tuple'>
print(self.client_address)           # ('127.0.0.1', 51520)
print(len(self.client_address))      # 2
```

**是元组（tuple），不是列表** —— `(host, port)` 结构，所以 `[1]` 取的是**客户端端口**。
它来自 `socket.accept()` 的返回值（`socketserver.TCPServer.get_request()` 把它交给 handler）。

> **`x[i]` 这个"下标语法"并不专属于列表** —— 只要对象实现了 `__getitem__` 就能用 `[]`：
> `list` / `tuple` / `str` / `bytes` / `dict`（按键）/ numpy 数组 / 自定义类……**具体行为由 `__getitem__` 决定**。

**⚠️ IPv6 下 `client_address` 是 4 元组**：`(host, port, flowinfo, scope_id)` —— `[1]` 取端口仍正确，但**解构时要注意**：

```python
host, port = self.client_address          # ❌ IPv6 下报 "too many values to unpack"
host, port = self.client_address[:2]      # ✅ 切片取前两个
host, port, *_ = self.client_address      # ✅ 星号兜住多余元素
```

**标准库自己就是这么写的** —— `BaseHTTPRequestHandler.address_string()`：

```python
def address_string(self):
    host, port = self.client_address[:2]      # ← 用 [:2] 而不是 [0], [1]
    return socket.getfqdn(host)
```

**本项目 `log_message` 里调用的 `self.address_string()` 就是它** —— 顺着这条线可以直接看到标准库的写法，这是个很好的"读源码"入口。

---

## 四、最终修复（三处，缺一不可）

| 改动 | 位置 | 作用 |
|---|---|---|
| `_read_json()` 加缓存 | `_read_json` | rfile 是流，读一次就没了；缓存让"入口消费"与"handler 取用"共享同一份数据 |
| **分发入口无条件消费 body** | `do_POST` / `do_GET` / `do_PUT` 首行调 `_consume_body()` | 保证任何分支（含提前 return）都不留未读 body |
| **每个请求重置缓存** | `handle_one_request` | 实例属性会在请求间泄漏，必须按请求重置 |

**验证**（临时诊断脚本，5/5 符合预期）：

```
① 正常登录                 → 200 ✅
② 无 token 下单（带 body）  → 401 ✅
③ 同连接再发 GET（无 token） → 401 ✅   ← 修复前是 400 Bad request syntax
④ 同连接再登录             → 200 ✅
⑤ 连续 5 次 GET            → 全部 401 ✅
```

全量用例：**18 / 18 通过**。

### 另一种解法：「在每个 `return` 前先读 body」行不行？

**行，逻辑上成立 —— 但它有四个会漏的地方。**

```python
def _handle_create_order(self):
    body = self._read_json()      # ← 先读 body
    if not self._is_authed():
        self._send(401, ...)
        return                    # ← 再 return
    ...
```

**顺序是对的**（读在鉴权之前）。但它要求「**每一个提前 return 的分支都记得先读**」—— 数一下本项目有多少个：

| handler | 提前 return 的分支数 |
|---|---|
| `_handle_register` | 1（name 非法） |
| `_handle_login` | 2（缺参数 / 密码错） |
| `_handle_create_user` | 2（未登录 / name 非法） |
| `_handle_get_user` | 3（未登录 / id 格式错 / 用户不存在） |
| `_handle_create_order` | 3（未登录 / 缺参数 / 用户不存在） |
| `_handle_update_user` | 4（未登录 / 缺参数 / id 格式错 / 用户不存在） |

**十几个点，全靠自觉。** 而且还有三个它**必然漏掉**的地方：

1. **404 兜底分支** —— `do_POST` 最后的 `else: self._send(404, ...)`：一个未知路径的 POST（带 body）照样残留。
   **这是框架层的位置，不在任何 handler 里，你根本不会想到去那里读 body。**
2. **GET / PUT 路径** —— 目前 `do_GET` 里没有任何 handler 读 body（GET 通常无 body），但 HTTP **允许** GET 带 body，一旦出现即残留。
3. **将来新增的 handler** —— 新人加一个分支，不会知道"这里要先读 body"。

**⇒ 本质区别**：

> **「消费请求体」是 HTTP 分帧的职责（框架级），不是业务逻辑的职责。**
> 把它下放到每个 handler，等于让**每一个业务分支**都承担一项**协议正确性义务** —— 迟早会漏。

这和本项目其他几处修正是**同一个思维**：

| 曾经的做法 | 修正后 | 共同点 |
|---|---|---|
| 应用层 `SELECT` 再 `INSERT` 查重 | **数据库唯一索引** | 把"记得遵守"变成"不可能违反" |
| 每个用例自己记得隔离数据 | `created_user` fixture **默认隔离** | 同上 |
| 每个 `return` 前记得读 body | **分发入口统一消费** | 同上 |

> **能"强制"就不要"约定"。** —— 这是防御式设计的核心。

**✅ 两种写法可以并存**：入口 `_consume_body()` 负责**分帧**，handler 里的 `_read_json()` 负责**取数据** —— 因为有缓存，第二次调用零成本。

### ❓ `_consume_body` 能省掉吗？直接在 `do_POST` 里调 `_read_json()` 不行吗？

**能 —— 功能上完全等价。** 因为 `_consume_body()` 内部就一行：

```python
def _consume_body(self):
    self._read_json()
```

```python
# 写法 A（当前实现）
def do_POST(self):
    self._consume_body()

# 写法 B（完全等价）
def do_POST(self):
    self._read_json()      # 扔掉返回值
```

**两者字节级行为一模一样。** 那保留 `_consume_body` 的价值是什么？—— **三件事**：

1. **命名即文档**
   ```python
   self._read_json()      # 读者：这里读 JSON 干什么？返回值还扔了？
   self._consume_body()   # 读者：把 body 消费掉 —— 意图一目了然
   ```
   **一行代码的方法，价值不在代码量，而在给这段逻辑起了名字。**

2. **命名防御（很实际）**
   将来有人做"清理无用代码"，看到 `self._read_json()` 的返回值没人用，可能**顺手删掉** → bug 复发 ❌
   而 `self._consume_body()` 这个名字会让人不敢动它。

3. **留一个"接缝"（seam）**
   若将来要做生产级加固（**只读字节、不解析 JSON**），只需改 `_consume_body` 内部一处：
   ```python
   def _consume_body(self):
       self._read_raw_body()      # 所有调用点一行都不用动
   ```

**⚠️ 但边界也要说清：不是所有一行代码都该包成方法。**

判据：**方法名是否承载了「读者一眼看不出来的信息」**。

| 例子 | 该不该包 | 理由 |
|---|---|---|
| `_consume_body()` 包 `_read_json()` | ✅ **该** | 说明了"这是**分帧**动作，不是取数据" |
| `_get_users()` 包 `return self.users` | ❌ 不该 | 没新增任何信息，纯噪音 |

**更精细的分层（生产环境值得做）**：分帧只需要「**把字节读掉**」，并不需要「**解析 JSON**」——

```python
def _read_raw_body(self):
    """只把字节消费掉（供分帧），不解析"""
    length = int(self.headers.get("Content-Length") or 0)
    return self.rfile.read(length) if length > 0 else b""
```

**好处**：鉴权前**不解析不可信输入**（未登录的请求不该触发 JSON 解析的开销与风险）。
**但必须限制 body 大小** —— 否则一个 `Content-Length: 999999999` 的请求就能把内存吃光；真实服务应返回 **413 Payload Too Large**。（这是 `Content-Length` 的经典攻击面，Mock 场景不涉及，属知识储备。）

---

## 五、三条可迁移的规律

1. **流式协议 + 自定界（`Content-Length`）的纪律**
   > **任何"提前返回"都必须保证输入流已被消费到本次消息的边界。**
   否则下一条消息会从错误位置开始解析。
   同一道理适用于 Redis RESP、length-prefixed 自研协议、消息队列（未 ack 的消息会阻塞后续）。

2. **框架的"对象生命周期"要查证，不能靠直觉**
   > `socketserver` 是「**每连接**一个 handler 实例（循环处理多个请求）」，不是「每请求一个实例」。
   > **一旦打开长连接，所有"请求级"的实例属性都必须显式按请求重置。**

3. **"以前没出问题" ≠ "以前是对的"**
   > 短连接（HTTP/1.0）同时掩盖了两类缺陷：**body 未消费**、**实例属性跨请求泄漏**。
   > **协议默认值一改，隐含假设全变** —— 这类"基础设施改动"必须做全量回归，不能只跑冒烟。

---

## 六、诊断线索速查

看到这些，可以直接往"分帧 / 连接复用"方向查：

| 线索 | 含义 |
|---|---|
| 响应体是 **`<!DOCTYPE HTML>` 的标准库错误页**（而非业务 JSON） | 请求在 `parse_request` 阶段就失败，**没过你的 handler** |
| 错误消息里**两段内容拼在一起**（如 `{...}GET /api/xxx HTTP/1.1`） | **上一条请求的 body 残留**，读指针错位 |
| 报"缺少参数"但客户端**明明发了** | handler 读到的是**别的请求的 body**（请求级状态未重置） |
| 用例**单独跑绿、一起跑红** | 顺序耦合：多半是**共享连接 / 共享状态**被前一条用例改过 |

---

## 七、面试话术（约 1 分钟）

> "我把 Mock 服务的 `protocol_version` 从默认的 HTTP/1.0 改成 HTTP/1.1 来启用连接复用。改完单跑没问题，但全量跑出现一条 401 变成 400 —— 而且那个 400 的响应体是**标准库的 HTML 错误页**，说明请求压根没进我的 handler。细看错误消息，服务端把**上一条请求的 JSON body 和这一条的请求行拼在一起**解析了。
>
> 根因是**长连接下请求体必须被完整消费**：我有几个 handler 是「鉴权失败就提前 return」，而读 body 写在鉴权之后，于是请求体残留在 socket 里，污染了下一条请求。**HTTP/1.0 每个响应后关连接，这个缺陷被完全掩盖了。**
>
> 修的时候我还踩了第二个坑：给 body 读取加了实例级缓存，却忘了**同一个 handler 实例会服务同一条连接上的多个请求**（`socketserver` 的 `handle()` 是 while 循环），缓存跨请求泄漏，一度把测试通过率搞到 38%。最后在 `handle_one_request` 里按请求重置才解决。
>
> 这件事让我记住两点：**一是流式协议里任何提前返回都得先把输入流消费到消息边界；二是"以前没出问题"不等于"以前是对的" —— 改协议默认值会把一批隐含假设一次性推翻，必须全量回归。**"

---

## 八、建议补的回归用例

这个缺陷**必须有用例守住**，否则下次谁加一个"提前 return 的 handler"就会复发：

```python
def test_keepalive_body_not_polluted(unauth_client):
    """回归：鉴权失败且带 body 的 POST，不应污染同一条连接上的下一条请求

    必须用同一个 client（= 同一条连接）才能复现；
    换成两个独立 client 就永远测不出来。
    """
    # ① 先制造残留：带 body 的 POST，且鉴权失败会提前 return
    r1 = unauth_client.post("/api/orders", json={"user_id": 1, "product": "x", "amount": 1})
    assertions.assert_status_code(r1, 401)
    # ② 同一条连接再发 GET：必须是 401，而不是标准库抛的 400
    r2 = unauth_client.get("/api/users")
    assertions.assert_status_code(r2, 401)
```

**变异测试自检**：把 `do_POST` 里的 `self._consume_body()` 注释掉 → 这条用例**必须变红**；恢复后**必须变绿**。
（这是确认用例真正有效、而非"恰好通过"的唯一办法。）
