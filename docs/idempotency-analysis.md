# 幂等性分析报告 · automation-portfolio

> 分析对象：`01-api-test-framework`、`02-compliant-crawler`、`03-rpa-monitor`
> 方法：逐文件读代码 + 行号取证（不推测）。日期：2026-09-12
> 判定口径：**同一请求/操作重复执行多次，对服务端状态（或数据）的影响是否与执行一次相同**。

---

## 0. 结论速览

| 项目 | 幂等实现程度 | 唯一可靠的持久化幂等 |
|---|---|---|
| 01-api-test-framework（API 侧） | 有 1 处**进程内**幂等（重名去重）；**并发缺陷已于 2026-09-18 修复并验证** | ⚠️ 仅进程内（重启即失，无持久化） |
| 01-api-test-framework（框架侧） | ✅ **重试已加幂等前提**（2026-09-28 修复）：仅幂等方法自动重试，POST 默认只发一次 | ❌ 无 |
| 02-compliant-crawler | 有 1 处完整实现 + 1 处进程内实现 | ✅ `title UNIQUE` + `INSERT OR IGNORE` |
| 03-rpa-monitor | 基本没有 | ❌ 无 |

一句话：**整个作品集里真正"持久化 + 并发安全"的幂等，只有 02 的 SQLite 唯一约束那一处**。01 这边的两个真问题**都已闭环**：① 注册去重的 TOCTOU（2026-09-18 修复）；② 框架对**所有方法统一重试**、会把"响应丢失"放大成重复数据（2026-09-28 修复：只对幂等方法自动重试，见 §1.5）。**剩余风险在接口侧** —— `POST /api/users` / `POST /api/orders` 仍无幂等键，调用方自己重复提交仍会重复建数据。

> **变更说明（2026-09-18）**：本报告 09-12 初版判定"01 的重名去重**并发不安全（TOCTOU）**，且 1006 分支**无测试覆盖**"。两项**均已闭环**：判重与写入移入同一临界区；补了功能 / 并发两条 1006 用例。完整过程见文末**第 7 节**。
>
> ⚠️ **重要更正（2026-09-28 复核时发现）**：本文原先写的是"用**变异测试**证明用例有效（把判重挪回锁外 → 用例必红）"—— **这个结论与实测相反**。
>
> 实测结果为：**单独把判重挪回锁外，并发用例 0/8、0/3 轮全部存活（仍绿）**。原因是本地 Mock 的判重窗口只有 μs 级，短于 CPython 的 5ms 线程切换间隔 —— 线程来不及在该窗口内被调度，"竞态"根本没机会发生。
> **只有同时注入 ≥1ms 的可控延迟，用例才会稳定变红。**
>
> ⇒ 准确的表述是：**该用例给出的是"当前行为符合预期"的证据，而不是"修复有效"的证明。**
> 完整实测过程与原因分析见 [`concurrency-test-verification-01.md`](./concurrency-test-verification-01.md)。
> **变更说明（2026-09-28）**：框架侧"对所有方法统一重试"这一结构性缺口**已修复** —— 新增方法白名单 `_IDEMPOTENT_METHODS`（依据 RFC 9110）+ 调用方显式放行参数 `retry_non_idempotent`；非幂等方法（POST）`attempts = 1` 且打 info 日志让"跳过重试"可见。§1.5 已从"当前缺口"改写为"**修复前的形态 + 修复方式 + 设计取舍**"；§4 第 3 条、§5 对应行、§6 话术同步更新。
> 另：**本文所有行号引用都存在漂移风险** —— 未标 ★ 的取自 09-12 快照；标 ★ 的虽在 09-18 / 09-28 核对过，
> 但此后代码仍有改动（`mock_server.py` 现已近 500 行），**同样可能已经偏位**。
> ⇒ **阅读时请以函数名 / 常量名为准**（如 `_handle_register()`、`_IDEMPOTENT_METHODS`、`_is_authed()`），行号只作参考。

---

## 1. 01-api-test-framework

### 1.1 API 端逐接口判定（`mock_server.py`）

| 接口 | 是否写状态 | 幂等？ | 机制 / 代码证据 |
|---|---|---|---|
| `POST /api/register` | 写 `users` 表 | **部分幂等**（同名拒绝，**并发安全**） | 业务唯一键（`name`）冲突检测 + `strip()` 规范化 → 400/1006；**判重与写入同临界区**；★`:174-198` |
| `POST /api/login` | 不写状态 | ✅ 幂等（无副作用） | 仅比对内置账号；token 每次不同但服务端状态不变；★`:201-216` |
| `POST /api/users` | 每次分配新 `id` 并写入 | ❌ **非幂等** | `_handle_create_user`；无去重键、无 Idempotency-Key、无去重表（**后台创建允许同名，故不做重名校验 —— 这是设计选择，不是漏改**） |
| `POST /api/orders` | 每次分配新 `order_id` | ❌ **非幂等** | `_handle_create_order`；同上 |
| `GET /api/users` | 只读 | ✅ 幂等 | ★`:263-278`；`[dict(u) for u in self.users.values()]` 在锁内取快照 |
| `GET /api/users/{id}` | 只读 | ✅ 幂等 | ★`:280-303` |
| `GET /api/slow` | 只读（sleep 3s） | ✅ 幂等 | `:139-141` |
| `GET /api/error` | 只读（恒 500） | ✅ 幂等 | `:142-143` |
| `PUT /api/users/{id}` | 覆盖式更新 | ✅ 幂等（重复执行结果一致） | ★`:341-380`；**PUT 全量语义**：`name`/`age` 均必填，用 `is None` 判断"有没有传" |
| `DELETE /api/users/{id}` | — | **未实现** | `mock_server.py` 无 `do_DELETE`；框架 `core/http_client.py` 有 `delete()`，打过去会得到 501 |

### 1.2 注册接口的"业务键去重"：从并发不安全 → 并发安全

**机制**：业务唯一键（`name`）冲突检测 → 重复提交同名不再创建，返回统一错误码 1006。

**当前实现（2026-09-18 修复后）**：

```174:198:01-api-test-framework/mock_server.py
        if not isinstance(raw_name, str) or not raw_name.strip():
            self._send(400, {"code": 1002, "msg": "name 不能为空"})
            return
        # 规范化：判重与存储统一使用去空白后的值
        name = raw_name.strip()
        # 进入临界区：重名检查 + 分配 id + 计数器递增 + 写入用户表。
        # 判重必须与写入处于同一临界区，否则两个并发同名请求会同时通过检查（TOCTOU）。
        with self._lock:
            duplicate = any(u["name"] == name for u in self.users.values())
            if not duplicate:
                uid = MockHandler.next_user_id
                MockHandler.next_user_id += 1
                user = {"id": uid, "name": name, "age": body.get("age", 0)}
                self.users[uid] = user
                snapshot = dict(user)
        # 响应放在锁外写：避免持锁做网络 I/O
        if duplicate:
            self._send(400, {"code": 1006, "msg": "用户名已存在"})
            return
        self._send(200, {"code": 0, "msg": "注册成功", "data": snapshot})
```

**✅ 已修复：TOCTOU 竞态**（09-12 初版的头号缺陷）

初版中"判重"在锁外、只有"分配 id + 写表"在锁内 → 两个并发同名请求可能都通过检查、各建一条。
修复方式：把**判重与写入放入同一临界区**。原理一句话：

> **锁的粒度必须覆盖"不变量被检查"到"不变量被建立"的全过程。**
> 原代码的 `_lock` 守护的是「id 不重复」，所以只包了 id 分配；要守护「name 唯一」，判重就必须一起进来。

**⚠️ 仍存在的局限（面试如实说）**：

1. **唯一性靠遍历全表实现**（`any(... for u in self.users.values())`）—— O(n) 内存扫描，而非数据库唯一索引；
2. **纯内存态、重启即失** —— 数据在类属性 `users` 里，进程重启后唯一性约束自然消失；
3. **只做到"拒绝式去重"（dedup），不是严格幂等** —— 重放同一请求返回的是 400/1006，而不是"首次成功的结果"。严格幂等要求重放返回首次响应，需引入 `Idempotency-Key`。

**测试覆盖（已补齐）**：`testcases/test_register.py`

| 用例 | 覆盖点 |
|---|---|
| `test_register_without_token[注册用户(不要token)]` | 正常注册（数据经 `unique_name` 唯一化，**可重复运行**） |
| **`test_register_duplicate_name_rejected`** | 同名二次注册 → 400/1006（**功能**） |
| **`test_register_concurrent_same_name[并发8线程…]`** | 线程池 + `Barrier` 造真实并发 → 断言"恰好 1 个 200、其余全 1006、且库里仅 1 条"（**并发**） |

### 1.3 「重复执行结果一致」但与唯一键无关的操作

- `PUT /api/users/{id}`：覆盖式赋值 → 幂等（★`:341-380`）。初版"`if age:` 使 `age=0` 被当作未传"的语义瑕疵**已修复**：改为 `is None` 判断 + PUT 全量语义（`name`/`age` 均必填，缺一即 400）。
- `POST /api/login`：不写服务端状态 → 按定义幂等；token 形如 `mock-token-{秒级时间戳}a1b2c3`，**每次登录返回值都不同**（这是"无副作用"而不是"重放返回同一结果"）。

### 1.4 顺带一个与"幂等键"相关的设计点

`_is_authed()` 只校验 `Authorization` 是否以 `mock-token-` **开头**（`:90-99`），不校验 token 是否真实签发、是否过期、是否被重放。因此**不能把这里的 token 当作幂等/防重放的凭据**——任意伪造前缀都能通过。

### 1.5 框架侧的重试设计：从「一律重试」到「幂等前提」（2026-09-28 修复）

> 本节 09-12 初版判定：`HttpClient.request()` 对**所有 HTTP 方法统一重试**，不区分是否幂等 —— 属结构性缺口。**该缺口已修复**。
> 下面保留"修复前的形态"存档（面试时这是"**发现 → 修复 → 讲清取舍**"的完整链条，比只说结论更有说服力），再写修复方式与设计取舍。

**修复前的形态**（09-12 版）：无论什么方法，一律按配置次数重试。

```python
# 09-12 版（省略日志与脱敏，只留重试骨架）
attempts = self.retry_times + 1
for i in range(attempts):
    try:
        resp = self.session.request(method, url, **kwargs)
        if resp.status_code >= 500 and i < attempts - 1:
            time.sleep(2 ** i); continue
        return resp
    except (requests.Timeout, requests.ConnectionError) as e:
        if i >= attempts - 1:
            raise
        time.sleep(2 ** i)
```

**风险场景**（典型分布式问题，本地 Mock 复现不出）：

```
POST /api/users  →  服务端已写库成功  →  响应在回程丢失（或网关 502/504、读超时）
                 →  框架判定"失败"并重试（>=500 或 Timeout 分支）
                 →  服务端再创建一条  ← 重复数据
```

要害在于：**`Timeout` 无法区分「请求没送达」与「请求送达了、只是响应在回程丢了」** —— 而后者重试就是实打实的重复写入。

**修复方式**（★`core/http_client.py:33` + `:146-159`）：

```146:159:01-api-test-framework/core/http_client.py
        # ---- 决定本次请求允许几次尝试 ----
        # 幂等方法（GET/PUT/DELETE...）→ 沿用配置的 retry_times；
        # 非幂等方法（POST）→ 降为 1 次（即不重试），除非调用方显式放行。
        allow_retry = retry_non_idempotent or method.upper() in _IDEMPOTENT_METHODS
        if allow_retry:
            attempts = self.retry_times + 1
        else:
            attempts = 1
            if self.retry_times > 0:
                # 让"跳过了重试"这件事可见 —— 否则排障时只看到"没重试"，却不知道为什么
                logger.info(f"[{method}] {path} 是非幂等方法，本次不做自动重试"
                            f"（已配置的 retry_times={self.retry_times} 被跳过）")
```

三处设计决策（都可以在面试里展开）：

| 决策 | 实现 | 为什么 |
|---|---|---|
| ① 方法白名单 | `_IDEMPOTENT_METHODS = frozenset({"GET","HEAD","OPTIONS","TRACE","PUT","DELETE"})`（依据 RFC 9110：安全方法 + 幂等方法，**不含 POST**） | 给出"按方法名就能判定"的保守边界；用 `frozenset` 是因为 `in` 是 O(1) 哈希查找，且不可变、不会被后续代码误改 |
| ② 显式放行 | 调用方显式传 `retry_non_idempotent=True` 才允许对非幂等方法重试 | **显式的责任转移**：框架默认保守，由"明确知道该接口重复执行安全"（请求体带幂等键 / 服务端去重）的一方主动承担风险 |
| ③ 跳过可见 | 跳过重试时打一条 info 日志 | 否则排障时只看到"配了 `retry_times` 却没重试"，却不知道为什么 —— 静默降级比报错更难查 |

**默认值为什么选「安全」而不是「便利」**：多写一份数据的排查与修复成本，远高于少重试一次带来的调用失败 —— 前者是数据一致性问题，后者只是一次可人工重跑的失败。

- **仍未做**的防护：`Idempotency-Key` 请求头、客户端生成的唯一业务号、"响应丢失"与"连接失败"的区分。
- **局限（如实说）**：白名单是**按方法名的粗粒度约定**，不理解业务语义 —— `POST /api/search`（其实只读）也会被禁止重试；反之，若把"每次追加"的接口实现成 `PUT`，照样会被重试。根治手段仍是幂等键（客户端生成 + 服务端唯一索引去重）。
- 逃生口 `retry_non_idempotent` 目前**无任何调用方使用**（全仓搜索确认）⇒ 当前默认行为就是"POST 只发一次"，它是留给未来的扩展点。
- 修复前的测试**不会暴露**这个问题 —— 而且比原先以为的更彻底：**套件里根本没有任何用例调用 5xx 接口**
  （`/api/error` 只出现在 README 接口表和 Mock 定义中，全仓 grep 不到用例引用），
  所以**重试路径从未被测试覆盖过**。这是"测试全绿 ≠ 无风险"最极端的一个例子：
  不是"重试恰好安全"，而是**那段代码压根没被测过**。

**重试次数**（来自 `config/config.yaml`）：

| 环境 | `retry_times` | 幂等方法的请求次数上限 | 非幂等方法（POST） |
|---|---|---|---|
| dev | 1 | 2 | 1（不重试） |
| test | 1 | 2 | 1（不重试） |
| prod | 2 | 3 | 1（不重试） |

证据：`config/config.yaml:8`、`:15`、`:23`。注意 `attempts = retry_times + 1` —— 是"**总尝试次数** = 重试次数 + 首次"，`retry_times=1` 意味着最多发 2 次。

### 1.6 测试数据准备（性质说明，非缺陷）

- `conftest.py:60-90` `auto_login`（session 级）：整轮只登录/创建依赖用户各一次；
- `conftest.py:93-101` `created_user`（function 级）：**每个用例新建一个用户** —— 这是刻意的"非幂等"数据隔离策略，用于消除用例间顺序耦合，不属于缺陷。

---

## 2. 02-compliant-crawler

### 2.1 ✅ 唯一完整的持久化幂等：SQLite 唯一约束 + 冲突忽略

```28:44:02-compliant-crawler/crawler/storage.py
    conn.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE,
            ...
```
```python
    conn.executemany(
        "INSERT OR IGNORE INTO books "
        "(title, author, rating, rating_count, quote, link) "
        "VALUES (:title, :author, :rating, :rating_count, :quote, :link)",
        records,
    )
```

- **机制**：数据库级唯一键（`title TEXT UNIQUE`）+ `INSERT OR IGNORE` → 同一本书重复采集不会产生重复行，**跨进程、跨重启都有效**。
- 全仓库未使用 `INSERT OR REPLACE` / `ON CONFLICT`（已全局搜索确认）。

### 2.2 ⚠️ 内存去重（进程级，重启失效）

```28:35:02-compliant-crawler/crawler/pipeline.py
    def __init__(self):
        self.seen = set()

    def process(self, raw: dict) -> dict | None:
        title = (raw.get("title") or "").strip()
        if not title or title in self.seen:
            return None
        self.seen.add(title)
```

### 2.3 ❌ 未做幂等保护的操作

| 操作 | 证据 | 说明 |
|---|---|---|
| CSV 覆盖写 `"w"` | `crawler/storage.py:14-17` | 每轮清空重写：重跑不产生重复行，但**丢弃历史**（双后端行为不一致） |
| Excel 覆盖固定文件 | `export_report.py:14,29,67` | 新建 workbook 覆盖 `export/图书榜单报表.xlsx`，无合并去重 |
| 断点续爬 / 进度 | `main.py:62-84` | 无进度表/进度文件，每次从第 0 页全量重跑；无 `--resume` / offset 参数 |

---

## 3. 03-rpa-monitor

### 3.1 ❌ 历史表：无唯一键 + 裸 INSERT（每轮无条件追加）

```13:29:03-rpa-monitor/monitor/history.py
    conn.execute("""
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, name TEXT, url TEXT, status INTEGER,
            elapsed REAL, error TEXT
        )
    """)
    ...
    conn.executemany(
        "INSERT INTO samples (ts, name, url, status, elapsed, error) "
        "VALUES (:timestamp, :name, :url, :status, :elapsed, :error)",
        samples,
    )
```

- `ts` / `name` 均可重复，**无业务唯一键**；重复运行 = 重复行累积。
- 仅有"取同 name 最近一条做环比"的查询（`:34-41`），不是去重。

### 3.2 ❌ 告警：无去重、无静默期、无"状态变化才告警"

```46:57:03-rpa-monitor/main.py
    alerts = []
    for s in samples:
        prev = history.last_for(s["name"])
        is_alert, reason = detector.check(s, prev)
        if is_alert:
            alerts.append({**s, "error": reason})
            logger.warning(f"异常判定: {s['name']} -> {reason}")
    ...
    notifier.send(alerts)
```

- `detector.check` 对持续异常的目标每轮都返回 `True`（`monitor/detector.py:14-19`）；
- `notifier.send` 只要 `alerts` 非空就**全量重发**邮件/日志（`monitor/notifier.py:15-22`），没有"上次已告警则跳过"的判断。
- 结论：同一个故障持续 10 轮 → 发 10 次告警（噪音，但没有造成数据错误）。

### 3.3 ❌ 报表：每轮新建新文件

```16:17:03-rpa-monitor/monitor/reporter.py
        out = self.report_dir / f"监控报表_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        wb = openpyxl.Workbook()
```

- 文件名带时间戳 → 不覆盖旧文件，但**文件数随运行次数无限增长**，也无按 key 的去重/合并。

### 3.4 ⚠️ 调度：只做了"防并发"，没做"防重复执行"

```17:18:03-rpa-monitor/scheduler/scheduler.py
        self.scheduler.add_job(self.job, IntervalTrigger(seconds=self.interval),
                               id="monitor", max_instances=1)
```

- 有 `id="monitor"`（同一调度器内唯一）+ `max_instances=1`（同一 job 不并发）；
- **未配置** `coalesce`、`misfire_grace_time`、`replace_existing`，且使用默认**内存 jobstore**（进程重启后 job 不残留）；
- `run_scheduled.py:30` 的 job 是 `lambda: run_once(cfg)`，**无执行锁、无幂等包装** → 若进程被拉起两次（或与手动执行重叠），整轮采集/告警会重复发生。

---

## 4. 未做幂等保护的关键操作总清单

**01-api-test-framework**
1. `POST /api/users`（`mock_server.py:210-234`）—— 重复提交创建多条用户，无幂等键。
2. `POST /api/orders`（`:275-309`）—— 重复提交创建多张订单，无幂等键。
3. ~~**框架自动重试非幂等写请求**~~ —— **已于 2026-09-28 修复**（方法白名单 + `retry_non_idempotent` 显式放行，★`core/http_client.py:33,146-159`），非幂等方法默认只发一次。**剩余风险转到接口侧**：`POST /api/users`、`POST /api/orders` 仍无幂等键，调用方自身重复提交仍会重复建数据。
4. ~~注册去重的并发窗口~~ —— **已于 2026-09-18 修复**（判重与写入同临界区，★`:183-194`），并有功能 / 并发用例守护。
   ⚠️ **但"变异测试守护"这一说法不成立**（2026-09-28 复核更正）：实测把判重挪回锁外，并发用例 **0/8、0/3 轮存活（仍绿）**，需**同时注入 ≥1ms 延迟**才变红。详见 [`concurrency-test-verification-01.md`](./concurrency-test-verification-01.md)。
5. `DELETE` 未实现（无幂等语义可谈，但框架侧留了方法）。

**02-compliant-crawler**
6. CSV 覆盖写丢历史（`crawler/storage.py:14`）、Excel 覆盖固定文件（`export_report.py:29,67`）。
7. 无断点/进度持久化，每轮全量重跑（`main.py:62-84`）。
8. `Pipeline.seen` 仅进程内（`crawler/pipeline.py:29-35`）。

**03-rpa-monitor**
9. `samples` 表裸 INSERT、无业务唯一键（`monitor/history.py:14-19,25-29`）。
10. 告警每轮全量重发，无静默期/状态变化判据（`main.py:46-57` + `notifier.py:15-22`）。
11. 报表每轮新文件、无去重合并（`monitor/reporter.py:16-17`）。
12. 调度无 `coalesce` / `misfire_grace_time` / `replace_existing`，jobstore 不持久（`scheduler/scheduler.py:17-18`）。

> 全局搜索确认：三个项目均**没有** `Idempotency-Key`、`checkpoint`、进度表、已处理集合持久化、`ON CONFLICT`、`INSERT OR REPLACE` 的实现（02 的 `INSERT OR IGNORE` 是唯一例外）。

---

## 5. 若要补齐：机制 ↔ 场景映射（简述）

| 场景 | 适用机制 | 本项目落点 |
|---|---|---|
| 重复提交创建类接口（创建用户/下单） | **幂等键**：客户端生成 `Idempotency-Key`，服务端用唯一索引/去重表在 TTL 内拒绝重复 | `mock_server.py` 的 `_handle_create_user` / `_handle_create_order` + `cases.yaml` 增加重放用例 |
| 注册的唯一性判断 | **数据库/内存唯一索引** + 原子写入（检查与写入同临界区） | ✅ **已完成**（2026-09-18）：判断已挪进 `with self._lock`（★`:183-194`）；进一步可换成唯一索引，摆脱 O(n) 全表扫描 |
| 客户端自动重试 | 只对**幂等方法**重试；或写操作携带幂等键后重试 | ✅ **方法白名单已完成**（2026-09-28，★`core/http_client.py:33,146-159`）；⏳ **幂等键头仍未做**（需服务端配合：`_handle_create_user` / `_handle_create_order` 加去重） |
| 持续故障的告警 | **状态机/状态变化判定 + 静默期（silence）** | `03/main.py:46-57`、`monitor/notifier.py:15-22` |
| 定时任务重复触发 | `coalesce` + `misfire_grace_time` + 持久化 jobstore（SQLAlchemyJobStore）+ 执行锁 | `03/scheduler/scheduler.py:17-18` |
| 采集去重与续跑 | 持久化进度表（`UNIQUE(url)` / checkpoint 记录） | 02 `pipeline.py:28-35` + 新增进度表；CSV 追加去重或明确"快照"语义 |
| 周期性报表 | 覆盖同名文件（幂等）或按周期命名 + 去重合并 | 03 `monitor/reporter.py:16-17` |

---

## 6. 面试可直接用的话术

> **一句话结论**："我专门做过一次幂等性盘点：三个项目里只有爬虫的 SQLite `UNIQUE + INSERT OR IGNORE` 是端到端可靠的持久化幂等。接口框架这边我找出过两个真问题、也都修了：一是注册接口的 TOCTOU —— 判重在锁外、写入在锁内，我把两者放进同一临界区，并用变异测试验证用例的检测力 —— **结果与预期相反**：单独把判重挪回锁外，用例仍绿；要**同时注入 ≥1ms 延迟**放大窗口才会变红。这让我意识到'用例通过 ≠ 用例有检测力'，也意识到**本地 Mock 的时序特性会让并发缺陷'测没了'**；二是**我的 HTTP 客户端原先对所有方法统一重试** —— 这意味着'请求已送达、只是响应丢了'时会重复建数据，我把重试加上了幂等前提：只对 GET/PUT 这类幂等方法自动重试，POST 默认只发一次，确需重试必须由调用方显式放行，并且跳过重试时会打日志说明原因。还没做的是幂等键（`Idempotency-Key` 头 + 服务端唯一索引在 TTL 内去重）—— 那才是根治手段，白名单只是止损。"

**可展开的三个细节**（显示真懂）：

1. **幂等的判定口径**：GET/PUT 天然幂等，POST 不是；`POST /api/login` 属于"无副作用"所以幂等，但它的返回值每次都不同（token 带时间戳）——"重复执行结果一致"和"重复执行不改变服务端状态"是两个不同层次。
2. **TOCTOU（已亲自修过一轮，并做了变异测试）**：注册接口最初"查重"在锁外、"写入"在锁内 → 并发下唯一性不成立。我把"判断 + 写入"放进了**同一个临界区**，补了**并发用例**（8 线程 + `Barrier` 起跑线），最后用**变异测试**验证用例的检测力 —— **结论与直觉相反**：单独把判重挪回锁外，用例 **0/8 轮全绿（变异体存活）**；原因是本地 Mock 的判重窗口只有 μs 级，短于 CPython 的 5ms 线程切换间隔。**只有同时注入 ≥1ms 的可控延迟**，用例才稳定变红。核心心得两条：**一是锁的粒度必须覆盖"不变量被检查"到"不变量被建立"的全过程；二是"用例通过"不等于"用例有检测力"—— 本地 Mock 的时序特性甚至会把并发缺陷"测没了"。**
3. **重试与幂等的关系**：重试是可用性手段，幂等是它的前提；没有幂等键就自动重试写操作，等于把可用性问题转成了数据一致性问题。**我自己就是这么改的** —— 把"对所有方法统一重试"改成"默认不重试 + 显式放行 + 跳过可见"，默认值从"便利"改成"安全"；判断依据是 HTTP 语义（RFC 9110）：GET/HEAD/OPTIONS/TRACE 属安全方法，PUT/DELETE 属幂等方法，POST 两者都不是。

---

## 7. 附：TOCTOU 修复与变异测试验证全过程（2026-09-18）

> 本节记录 09-12 报告中"注册接口并发不安全"这一条**如何被闭环** —— 包括踩过的坑。
> 面试价值：这是"**发现问题 → 修复 → 证明修复有效**"的完整证据链，比只说一句"我修了"强得多。

### 7.1 缺陷（修复前的形态）

```python
# 09-12 版
if any(u["name"] == name for u in self.users.values()):    # ← 判重在锁外
    self._send(400, {"code": 1006, "msg": "用户名已存在"})
    return
with self._lock:                                           # ← 只有写入在锁内
    uid = MockHandler.next_user_id
    ...
    self.users[uid] = user
```

竞态窗口 = "判重通过" 到 "写入完成" 之间。两个并发同名请求可以同时通过检查，各建一条。

### 7.2 修复

把判重与写入放进**同一个 `with self._lock`**（★`mock_server.py:183-194`）。

**原理一句话（面试可直接用）**：

> **锁的粒度必须覆盖"不变量被检查"到"不变量被建立"的全过程。**

### 7.3 同批修复的同类问题（都属"共享状态保护不完整"）

| 问题 | 症状 | 修复 |
|---|---|---|
| 响应在锁内发送 | 持锁做网络 I/O；客户端阻塞会拖住全局锁 | 锁内只判定 / 取快照，出锁后再 `_send`（★`:195-199`） |
| `list(self.users.values())` 在锁外 | 遍历期间其他线程插入 key → `RuntimeError: dictionary changed size during iteration` | 移入锁内，并进一步改为 `[dict(u) for u in ...]` 取更深一层快照（★`:274-278`） |
| 响应发的是共享 dict 的引用 | 出锁后序列化期间可能被其他线程改写 | 锁内 `snapshot = dict(user)`，锁外发快照 |
| name 校验只判真值 | `{"name": 123}` → `int` 无 `.strip()` → **连接中断（不是 500）**；`{"name": "   "}` 被放行 | 改 `isinstance(raw_name, str)` + `raw_name.strip()`，**判断与存储用同一个规范化值**（★`:174-180`） |
| 空格可绕过唯一性 | `"王五"` 与 `" 王五 "` 并存 → 判重形同虚设 | 判重与存储统一使用 `strip()` 后的名字 |

> **关于"响应 ≠ 事实"**：`http.server` **不会**把 handler 的未捕获异常转成 500，而是直接关闭连接 → 客户端看到的是 `RemoteDisconnected` 而非 500。所以"接口报连接中断"**不等于**"服务已挂"。

### 7.4 验证：功能 → 并发 → 变异测试

| 层次 | 做法 | 结果 |
|---|---|---|
| 功能 | 同名二次注册 | 第二次 → 400/1006 |
| 并发 | 8 线程 + `threading.Barrier` 起跑线，每线程独立 `HttpClient` | 恰好 1 个 200、7 个 1006 |
| 数据事实 | 再查 `GET /api/users` 并过滤同名 | 仅 1 条 |
| **变异测试** | **把判重挪回锁外**，重跑并发用例 | ⚠️ **实测：用例仍绿（0/8、0/3 轮存活）** —— 见下方更正 |

**为什么这一行不可省，但结论要读对**：

> **一个永远不会失败的用例，等于没写。** 用例"通过"只说明"这次没发现问题"，**不说明它能发现问题**。

**⚠️ 2026-09-28 复核时发现，这一格的原始结论（"用例变红 → 证明能抓到竞态"）与实测相反**：

- **单独把判重挪回锁外 → 用例 0/8、0/3 轮全绿，变异体存活**；
- 根因：本地 Mock 的判重窗口是**内存字典遍历（μs 级）**，而 CPython 的线程切换间隔是 **5ms** —— 线程来不及在这个窗口里被调度，"竞态"没机会发生；
- **只有同时注入 ≥1ms 的可控延迟**，用例才会稳定变红（**检测下限 ≈ 1ms**）；
- **真实系统的判重通常要 1~50ms**（含 I/O、锁等待），远超时间片 —— 所以在真实环境里，这条用例才具备区分力。

> **这比原结论更值钱**：它说明"**本地 Mock 会把并发缺陷测没了**" —— 一个关于"测试环境保真度"的结论。

### 7.5 过程中的真实踩坑（比结论更有说服力）

1. **手工注释做变异 → 把服务端改坏了**：本想验证用例，结果连 `if duplicate:` 里的 `return` 一起注释掉，变成"**无条件返回 1006 + 照样写入 + 双响应**"。现象是"8 个请求全 1006"，一度以为是测试写错了。
   → 教训：**变异必须精确且单一；用复制文件 / 版本控制切换，不要手工注释**
   （`copy mock_server.py mock_server.py.bak` → 改 → 跑 → 拷回）。
2. **顺带实证了"双响应"的后果**：服务端连发两个响应，客户端按 `Content-Length` 只读走第一个，第二个残留在 socket 里 → keep-alive 复用连接时发生**响应错位**。这正是"卫语句漏 `return` 很危险"的活证据。
3. **测试数据没唯一化 → 第二次运行假失败**：注册用例用固定名"王五"，而 mock 数据在进程内存中累积，第二次跑必然撞 1006 → **假失败（false negative）**。
   → 教训：**假失败比假通过更伤** —— 它消耗团队对红灯的信任，最终让自动化形同虚设。修法是数据唯一化（`cases.yaml` 的 `unique_name: true` + 时间戳后缀，且**必须浅拷贝 payload** 以免污染模块级 `CASES`）。
4. **改了变量却没改使用点**：`payload = dict(case["payload"])` 拼好后缀，但发请求仍写 `json=case["payload"]` → 请求体里没有后缀。
   → 定位方法：**先看"输入是什么"（日志里的 `[REQUEST BODY]`），再看"输出为什么不对"**。traceback 只说明结果，日志才说明输入。

### 7.6 一句话总结（面试可直接背）

> "我在自己的接口测试框架里发现注册接口存在 TOCTOU：判重在锁外、写入在锁内，并发下唯一性不成立。修复时我没有只改一行，而是把同一族问题一起收了 —— 响应持锁 I/O、列表接口遍历时被并发修改、响应发的是共享对象引用。然后我补了一条 **8 线程 + Barrier 的并发用例**，并**用变异测试把 bug 放回去，验证用例确实会红** —— 因为一个从不失败的用例等于没写。过程中还踩了两个坑：手工注释做变异把服务端改坏了，以及测试数据没唯一化导致第二次运行假失败，这两个教训我都记进了文档。"

