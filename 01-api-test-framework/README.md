# 接口自动化测试框架

> 企业级接口自动化测试框架：**数据驱动 + 接口依赖传递 + 一键报告**。clone 即可运行，无需外网、无需付费服务。

## 功能特性

- **分层架构**：`core`（封装）/ `testcases`（用例）/ `data`（数据）/ `config`（配置）四层分离，工程化规范
- **接口依赖传递**：登录取 token → 创建用户取 id → 下单，变量池自动流转（接口自动化的核心难点）
- **数据驱动**：yaml 管理用例数据，一条数据一个用例，新增用例不写代码
- **统一断言库**：HTTP 状态码 + 业务码 + JSON 字段 + 字段类型 + 必填字段 + 响应耗时，全维度校验
- **多环境切换**：`pytest --env=dev/test/prod` 一键切换，接入真实环境只需改配置
- **幂等重试 + 超时控制**：仅**幂等方法**（GET/HEAD/OPTIONS/TRACE/PUT/DELETE）自动指数退避重试；
  **POST 默认只发一次** —— 避免"请求其实到了、只是响应丢了"时重试造成重复创建数据
- **自带 Mock 服务**：纯标准库实现，任何环境 clone 下来即可跑通
- **一键运行**：`python run.py` 自动起服务、跑用例、出 HTML 报告

## 接口与业务码

Mock 服务提供 9 个接口，覆盖 REST 风格的基础操作与两类特殊场景（慢响应 / 恒 500）：

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| `POST` | `/api/register` | ❌ | 公开注册 |
| `POST` | `/api/login` | ❌ | 登录，成功返回 token |
| `GET` | `/api/users` | ✅ | 用户列表 |
| `POST` | `/api/users` | ✅ | 创建用户 |
| `GET` | `/api/users/{id}` | ✅ | 查询单个用户 |
| `PUT` | `/api/users/{id}` | ✅ | 全量更新用户（`name`/`age` 均必填） |
| `POST` | `/api/orders` | ✅ | 下单（依赖已存在的 `user_id`） |
| `GET` | `/api/slow` | ❌ | 固定 3 秒（演示响应时间断言） |
| `GET` | `/api/error` | ❌ | 固定 500（演示异常场景） |

**业务码**（响应体里的 `code` 字段）：

| 业务码 | 含义 | 配套 HTTP | 出现场景 |
|---|---|---|---|
| `0` | 成功 | `200` | 所有成功响应 |
| `1001` | 未登录 / 用户名或密码错误 | `401` | 登录失败；需鉴权接口未携带合法 token |
| `1002` | 参数缺失或格式错误 | `400` | 缺字段、id 非数字、`name` 为空 |
| `1003` | 用户不存在 | `404` | 查询 / 更新单个用户 |
| `1004` | 接口不存在 | `404` | 未匹配到任何路由 |
| `1005` | 用户不存在，无法下单 | `400` | `POST /api/orders` |
| `1006` | 用户名已存在 | `400` | 重复注册 |
| `5000` | 服务器内部错误 | `500` | `/api/error` |

> ⚠️ **权威定义处是 [`mock_server.py`](mock_server.py) 的模块 docstring**（业务码就定义在那里）。
> 本表仅为便于阅读，可能存在滞后 —— 有疑问时以代码为准。

**已知契约瑕疵（如实记录，暂不修改）**：

- **`1003` 与 `1005` 语义重复**：都表示"用户不存在"，但配套 HTTP 状态不同（`404` / `400`）；
- **`1001` 一码多义**：同时表示"密码错误"与"未登录"；
- **`1002` 一码多义**：同时表示"缺参数"与"格式错误"。

> **为什么不改**：修改需要同步改动 5 处服务端发送点与 2 条用例断言，而收益仅为"契约更整洁"，
> 在封版阶段不划算。**但如实记录比假装没看见更有价值** —— 这也是写接口文档的真正意义：
> **它会逼你用"客户端视角"重新审视一遍契约**，把 review 时容易滑过的不一致照出来。

## 环境要求

- **Python >= 3.10**（源码使用了 `dict | None` 的 3.10+ 语法）
- 无需外网、无需付费服务（自带本地 Mock 服务）

## 环境准备（新人必读 · 四个必踩项）

> 以下四条都是真实踩过的坑，照做可少走 1 小时弯路。

### 1. 用虚拟环境，别让 `pip` 装到全局 Python

```bat
rem 本作品集三个项目共用「仓库根」的 .venv；若还没有，先在仓库根执行一次：
python -m venv .venv

rem 然后在 01-api-test-framework 目录里安装依赖（注意开头的 ..\ 指向仓库根）
..\.venv\Scripts\python.exe -m pip install -r requirements.txt

rem 或先激活再装：..\.venv\Scripts\activate.bat   然后 pip install -r requirements.txt
```

裸敲 `pip install` 有可能装进全局 Python，造成「明明装了却 import 不到」的版本混用问题。**显式带上解释器路径**最保险（在 01 目录下就是 `..\.venv\Scripts\python.exe -m pip ...`）——它不依赖"当前有没有激活虚拟环境"。

### 2. `requirements.txt` 必须保持 UTF-8 BOM，别用 `pip freeze >` 覆盖它

`requirements.txt` 里有中文注释，而 pip 读 requirements 文件时，**没有 BOM 就按系统 locale 解码**（中文 Windows = GBK），会直接报：

```
UnicodeDecodeError: 'gbk' codec can't decode byte 0x86 in position 66
```

文件已写入 **UTF-8 BOM** 规避（pip 见到 BOM 会按 UTF-8 读）。注意两点：

- **`pip freeze > requirements.txt` 会丢掉 BOM**，覆盖后需重新加回；
- 需要「精确复现环境」时用 **`requirements.lock.txt`**（各依赖的确切版本，CI 用的就是它），不要覆盖 `requirements.txt`：

```bash
pip install -r requirements.lock.txt      # CI / 新机器：装到的版本与开发机完全一致
```

两者分工：`requirements.txt` 声明「需要什么」（版本下限，人会改）；`requirements.lock.txt` 记录「实际装了什么」（精确版本，供 CI 复现）。

> **BOM 是什么**：文件开头的 3 个字节 `EF BB BF`，内容是零宽字符（U+FEFF），**肉眼完全看不见**——它的作用是告诉读取方「请按 UTF-8 解码」，所以别指望在编辑器里"看到"它（复制粘贴时也常被吞掉）。判定只能靠字节层手段。

**怎么确认 / 丢了怎么补回**（在 `01-api-test-framework` 目录下执行）：

```bat
rem ① 确认：期望输出 b'\xef\xbb\xbf'；若输出 b'# R' 之类，说明没有 BOM
..\.venv\Scripts\python.exe -c "print(open('requirements.txt','rb').read(3))"

rem ② 补回（幂等：已有 BOM 就跳过，不会加重复）
..\.venv\Scripts\python.exe -c "import pathlib; p=pathlib.Path('requirements.txt'); b=p.read_bytes(); b=b[3:] if b[:3]==b'\xef\xbb\xbf' else b; p.write_bytes(b'\xef\xbb\xbf'+b); print(p.read_bytes()[:3])"
```

也可以用编辑器：**VS Code** 右下角编码 → `Save with Encoding` → `UTF-8 with BOM`；**Win11 记事本** 另存为 → 编码选 `UTF-8 with BOM`；**Notepad++** 编码 → 转为 UTF-8-BOM。

> ⚠️ **别加两次**：双 BOM 会让 pip 报 `Invalid requirement: '\ufeff# Requires...'`（首行不再以 `#` 开头，被当成依赖去解析）。所以补 BOM 一定要"先判断再加"，上面 ② 那条命令本身就是幂等的。

**一句话原理**：纯文本文件不记录自己的编码，读取方（pip）只能猜——有 BOM 就按 UTF-8 读，没有就按系统 locale（中文 Windows = GBK）读。BOM 就是"开头贴的一张透明标签"。

### 3. 单独跑 `pytest` 前，先保证 Mock 服务在跑

`pytest` 会直接连 `config/config.yaml` 里的 `base_url`（默认 `http://127.0.0.1:8000`）。服务没起时的典型报错：

```
urllib3.exceptions.MaxRetryError: ... [WinError 10061] 由于目标计算机积极拒绝，无法连接
```

三种正确姿势：

```bash
python run.py                          # 推荐：自动起服务 → 跑用例 → 关服务
python mock_server.py --port 8000      # 终端 A：手动起服务，保持不关
pytest -m "not slow"                   # 终端 B：再跑用例(跳过慢用例)
```

> 现在跑用例前会做**服务预检**：连不上直接给一句人话提示（退出码 4），不再刷几十行异常栈。
> 只收集用例可加 `--collect-only` 跳过预检；临时绕过可设环境变量 `SKIP_SERVICE_CHECK=1`。

### 4. 终端中文乱码：设 `PYTHONUTF8=1`

单独跑 `pytest` 时，如果终端代码页和 Python 的输出编码对不上，会出现两种现象：

- 中文变成 `???` 或 `����`（字节编码被另一端按错误编码解读）；
- 用例名被转义成 `test_login[\u6b63\u786e\u8d26\u53f7...]`——这是 pytest 的兜底行为：输出流无法表示该字符时，转义成 ASCII 而不是崩溃（源码 `_pytest/_io/terminalwriter.py`）。

**PowerShell**（注意 `$env:` 前缀）：

```powershell
$env:PYTHONUTF8 = "1"             # 解释器 UTF-8 模式：stdout/stderr 全用 UTF-8
$env:PYTHONIOENCODING = "utf-8"   # 更直接的等效写法（指定所有标准流编码）
chcp 65001                        # 控制台代码页切 UTF-8（配合上面更稳）
pytest -m "not slow"
```

**cmd.exe**（用 `set` / `setx`，没有 `$env:` 这种写法）：

```bat
chcp 65001
set PYTHONUTF8=1
pytest -m "not slow"
```

**永久生效**（新开终端起效）：

```bat
setx PYTHONUTF8 1 （新开终端可能会设置失败（仍然取旧的环境变量副本），需要注销/重启电脑）
```

补充两点：

- **最省事的办法**：本地一律用 `python run.py`。它已经给 pytest 子进程设好 `PYTHONIOENCODING=utf-8`，所以经它运行的中文与 emoji（✅⚠️）从不乱码；
- **重定向到文件时同样要设**：`pytest --collect-only -q > reports\用例清单.txt` 会按系统编码写文件，不设 `PYTHONUTF8=1` 的话用 VS Code 打开就是乱码。

> 这类乱码只影响**显示**，不影响用例结果；`reports/*.log` 是显式按 UTF-8 写的，不受影响。

### 常见报错速查

| 报错信息 | 原因 | 处理 |
|---|---|---|
| `[WinError 10061] 目标计算机积极拒绝` | Mock 服务没启动 | 用 `python run.py`，或先起 `mock_server.py` |
| `UnicodeDecodeError: 'gbk' codec...` | requirements 文件缺 BOM | 确认文件首字节为 `EF BB BF`；别用 `pip freeze >` 覆盖 |
| 中文显示成 `???` 或 `\uXXXX` 转义 | 终端编码不是 UTF-8 | 见第 4 条：`chcp 65001` + `set PYTHONUTF8=1`（PowerShell 用 `$env:PYTHONUTF8="1"`），或直接用 `python run.py` |
| `ModuleNotFoundError: No module named 'xxx'` | 包装到了另一个解释器 | 用 `.venv\Scripts\python.exe -m pip install xxx` |
| `Fatal Python error: preconfig_init_utf8_mode: invalid PYTHONUTF8 environment variable value` | `PYTHONUTF8` **只接受 `0` / `1`**；写成别的值（如 `2`）、带引号（`"1"`）、带尾随空格都会让解释器在**启动前**直接 abort（一行 Python 都跑不了，`pip`/`pytest` 全废） | ① `echo [%PYTHONUTF8%]` 看真实值（方括号能暴露引号与空格）；② `setx PYTHONUTF8 1`；③ **注销重登**（见下方说明） |
| 接口报 `RemoteDisconnected` / `Connection aborted`（而非 500） | 服务**起来了**，但 handler 抛了未捕获异常、连接被服务端掐断——`http.server` **不会**把未捕获异常转成 500，所以客户端只看到"连接中断" | 别急着重启服务，先看 mock 服务终端的 `Traceback` |

> **改环境变量后为什么要注销**：环境变量是**进程启动时从父进程继承的内存副本**，运行期不回读注册表。
> `reg add`/`reg delete` 只改注册表、**不广播**；`setx` 会广播，但依赖接收方响应。
> 最可靠的收尾是**注销重登**（重登时由 winlogon 重新读取注册表构建全新环境块）。
> 另外：`setx` 不会回灌**已打开**的终端 —— 当前窗口需 `set "PYTHONUTF8=1"` 才立即生效，PyCharm 也要重启。

## 快速开始

> ⚠️ **虚拟环境在「仓库根」，不在本目录** —— 三个子项目共用同一套 `.venv`（见上方「环境准备」）。
> 下面统一用 `..\.venv\Scripts\python.exe` 调用；**若你已激活过 venv**，也可以直接简写成 `python`。

```bat
:: 0. 首次准备（在【仓库根】执行一次即可）
cd /d e:\ruanjian\Learn\WorkBuddy\automation-portfolio
python -m venv .venv
.venv\Scripts\activate
pip install -r 01-api-test-framework\requirements.txt

:: ── 以下命令都在 01-api-test-framework 目录下执行 ──
cd 01-api-test-framework

:: 1.【最常用】一键全跑（自动起 mock → 跑用例 → 出报告）
..\.venv\Scripts\python.exe run.py

:: 2. 手工跑（需先开 mock 服务）
..\.venv\Scripts\python.exe mock_server.py --port 8000      :: 终端 A
..\.venv\Scripts\python.exe -m pytest -m "not slow"         :: 终端 B：跳过慢用例，日常提速

:: 3. 常用筛选
..\.venv\Scripts\python.exe -m pytest -m slow                        :: 只跑慢用例
..\.venv\Scripts\python.exe -m pytest testcases/test_auth.py         :: 只跑单个文件
..\.venv\Scripts\python.exe -m pytest testcases/test_auth.py -k login :: 按名称过滤
..\.venv\Scripts\python.exe -m pytest --env=test                     :: 切换环境
..\.venv\Scripts\python.exe -m pytest -v                             :: 看每条用例名
..\.venv\Scripts\python.exe -m pytest --collect-only -q               :: 只收集不执行（查用例总数）

:: 4. 自定义端口（8000 被占用时 run.py 也会自动换）
..\.venv\Scripts\python.exe run.py --port 9000
```

**跑完看两处**：终端底部的「测试结果摘要」（通过率）+ `reports/report.html`（逐条明细，双击打开）。

## 运行效果

```
[*] Mock 服务已启动: http://127.0.0.1:8000
[*] 运行环境: dev | Mock 端口: 8000
[*] 开始执行测试用例 ...

....................                                                      [100%]
                              ↑ 20 条用例 = 20 个点

收集用例数: 20（其中未选中 0）
通过      : 20 ✅    失败: 0    通过率: 100.0%  ✅ 全部通过

[*] pytest 退出码: 0
[*] HTML 报告  : ...\reports\report.html
[*] Mock 服务已关闭
```

## 测试报告

三套报告，用途不同：

| 报告 | 生成方式 | 特点 |
|---|---|---|
| **HTML 报告** | `python run.py` | pytest-html，**自包含单文件，双击即可打开** |
| **JUnit XML** | `python run.py --junitxml` | 结构化结果，给 CI 画通过率趋势 |
| **Allure 报告** | `python run.py --allure` | **分层用例 + 步骤 + 附件**，最详细 |

### 看 Allure 报告

**依赖**：`allure-pytest`（Python 侧，已在 `requirements.txt`）+ **Allure 命令行**（需 Java 11+）。

> 只装了 Python 插件、没装命令行时，`run.py` 会**自动降级跳过渲染**（用例照常执行），只在终端提示一句。

```bash
# ① 跑用例并生成报告（内部：清空旧结果 → 收集 → 渲染到 reports/allure-report）
python run.py --allure

# ② 打开报告
allure open reports/allure-report
```

> ⚠️ **别双击 `reports/allure-report/index.html`** —— Allure 是「纯前端页面 + 异步加载 JSON」，用 `file://` 打开时浏览器**同源策略会阻止 JS 读取本地 JSON**，页面会空白。
> **必须通过 HTTP 访问**：`allure open <已生成的报告>`，或 `allure serve reports/allure-results`（后者不用先 generate，最快）。

**CI 侧**：Jenkins 用 **Allure 插件**渲染（插件自带运行时，节点上**不需要**装命令行）—— 见 `Jenkinsfile`。

## 持续集成（CI）

把「手动跑用例」升级为「持续测试」：仓库自带 `Jenkinsfile`，**已在本地 Jenkins 上实际跑通**——
拉代码 → 装依赖 → 起 Mock 服务 → 执行全量用例 → 产出 JUnit + Allure 报告 → 归档，**20/20 通过、构建绿**。

```bash
# 本地模拟 CI 行为（产出 JUnit XML + Allure 结果）
pip install allure-pytest
python run.py --env=test --ci

# 日常提速：跳过 slow 标记的用例（CI 则跑全量）
python run.py -m "not slow"
```

| 产出 | 路径 | 用途 |
|---|---|---|
| HTML 报告 | `reports/report.html` | 人看的完整明细（pytest-html） |
| JUnit XML | `reports/junit.xml` | Jenkins `junit` 步骤读取，画通过率趋势 |
| Allure 结果 | `reports/allure-results/` | Jenkins Allure 插件渲染成可交付报告 |

流水线设计要点：

- **退出码即构建状态**：`run.py` 直接返回 pytest 退出码，用例失败则构建变红，不存在「报告红、流水线绿」
- **每轮清空 Allure 结果目录**：否则新旧结果累积会让报告失真
- **缺少 `allure-pytest` 时自动降级**：报告增强不会拖垮整条流水线
- **多环境切换落地**：`--env=test` 而非改配置硬编码，接真实环境时用例零改动

> **完整接入步骤**（装 Jenkins → 装插件 → 配 Allure → 建任务 → 失败通知 → 排错手册 → **实战踩坑记录**）
> 见 [`docs/jenkins-ci-guide.md`](../docs/jenkins-ci-guide.md)。

## 目录结构

```
01-api-test-framework/
├── run.py                 一键运行入口（起 mock → 跑 pytest → 出报告，支持 --ci）
├── Jenkinsfile            CI 流水线定义（拉代码 → 装依赖 → 执行用例 → 归档报告）
├── mock_server.py         本地 Mock 接口服务（纯标准库，零依赖）
├── conftest.py            pytest 夹具：env / client / unauth_client / auto_login / created_user
├── pytest.ini             pytest 配置
├── requirements.txt       依赖声明（版本下限；含中文注释，必须保持 UTF-8 BOM）
├── requirements.lock.txt  依赖锁文件（确切版本，CI 用它复现环境；纯 ASCII 注释）
├── config/                多环境配置（dev/test/prod）
│   ├── config.yaml
│   └── loader.py
├── core/                  框架核心封装
│   ├── http_client.py     Session 封装：token 注入/超时/幂等重试（POST 不重试）/日志脱敏
│   ├── assertions.py      统一断言库
│   └── extractor.py       响应提取 + 变量池（接口依赖传递）
├── utils/                 日志 / 数据读取
├── data/cases.yaml        数据驱动用例数据
├── testcases/             用例层（auth / register / user / order 依赖链）
├── scripts/notify.py      构建失败时推送企业微信机器人（由 Jenkinsfile 的 failure 块调用）
├── perf/                  性能测试资产
│   ├── README.md          压测三轮修复的完整记录
│   ├── gil_demo.py        GIL 对并发影响的对照实验
│   └── jmeter/login-flow.jmx   JMeter 业务流计划（4 事务）
└── reports/               运行产物：HTML / JUnit XML / Allure 结果（git 忽略）
```

## 延伸阅读

`docs/` 目录下是本项目的过程记录与深度分析（都是实际问题驱动，不是教科书笔记）：

| 文档 | 内容 |
|---|---|
| [`keepalive-body-pollution.md`](../docs/keepalive-body-pollution.md) | HTTP/1.1 长连接下「请求体残留」导致请求错位：一次协议升级引发两个缺陷，以及怎么被自动化用例抓住（**含已落地的回归用例与变异自检结果**） |
| [`performance-test-01-jmeter.md`](../docs/performance-test-01-jmeter.md) | JMeter 性能测试实战：连接层 → 因果链 → 数据量退化，三轮修复 + 两次发现「测量工具本身在骗人」 |
| [`jmeter-01-quickstart.md`](../docs/jmeter-01-quickstart.md) | JMeter 上手速查（元件作用域、关联、断言、JTL 字段） |
| [`idempotency-analysis.md`](../docs/idempotency-analysis.md) | 幂等性分析：**去重 ≠ 幂等** |
| [`concurrency-test-verification-01.md`](../docs/concurrency-test-verification-01.md) | 并发用例验证：怎么写出「真的能抓到竞态」的用例 |
| [`01-notes-request-flow.md`](../docs/01-notes-request-flow.md) | 一次请求从客户端到 Mock 服务的完整流转笔记 |
| [`jenkins-ci-guide.md`](../docs/jenkins-ci-guide.md) | **Jenkins CI 接入全流程**：从装 Jenkins 到失败通知，附**实战踩坑记录**（17 个真实坑与解法） |

## 简历亮点

> 独立设计并实现接口自动化测试框架：基于 Requests + Pytest，支持数据驱动、多环境切换、接口依赖传递（变量池）、统一断言与性能断言；封装 HTTP 客户端实现鉴权注入、超时控制与**按方法区分的重试策略**（仅幂等方法自动重试，避免 POST 重放）；集成 pytest-html 报告与一键运行脚本，实现「clone 即跑」，覆盖登录鉴权、CRUD、业务异常、并发、性能等 20 条用例场景。
>
> **持续集成实践**：基于 Declarative Pipeline 搭建 Jenkins 流水线，实现「拉代码 → 装依赖 → 执行全量用例 → 归档报告」自动化，支持定时与提交触发；集成 Allure + JUnit 双报告体系并保留历史通过率趋势；通过退出码传递保证「用例失败即构建失败」，慢用例用 pytest marker 隔离实现日常/CI 执行策略分离。
