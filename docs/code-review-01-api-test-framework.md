# 代码评审报告 · 接口自动化测试框架（01-api-test-framework）

> 评审对象：`01-api-test-framework`
> 评审日期：2026-08-30
> 评审方式：全量源码静态阅读 + 跨仓符号引用核查（16 个 `.py`、2 个 `.yaml`、`pytest.ini`、`requirements.txt`、`.gitignore`、`docs/`）
> 评审原则：**只评价已核实的事实**，每条问题都标注 `文件:行号`。
> **修复进度（2026-08-30 更新）**：P0-1、P0-2、P1-10 已修复（均为配置层改动，无业务逻辑变更）；其余问题保持"只记录未改动"，见第 7 节。

---

## 0. 评审结论摘要

| 维度 | 评分 | 一句话评价 |
|---|---|---|
| 分层与工程化 | 8.5 / 10 | 四层分离干净，职责边界清晰，达到可对外展示的水平 |
| 可运行性（clone 即跑） | 9 / 10 | 纯标准库 Mock 服务 + 一键运行脚本，体验很好 |
| 代码质量 | 7 / 10 | 主体清爽可读，但存在硬编码与"亮点未落地"的细节缺口 |
| 健壮性 | 6.5 / 10 | 夹具失败路径、HTTP 客户端参数合并、用例耦合有待加固 |
| 交付完整性 | 6 / 10 → **8.5** | ~~**`.gitignore` 会吞掉 `data/cases.yaml`**~~ **已修复**；剩余扣分点：Python 最低版本未声明 |
| **综合** | **7.5 / 10** → **8 / 10** | 作品集里属于中上水准，工程化骨架是对的；修复 P0 后已可安全对外分发 |

一句话总评：**骨架是对的，甚至比很多"培训班项目"扎实——Mock 服务和一键运行脚本是真正的加分项；但有三处"对外承诺"与"代码实现"不一致（.gitignore 吞数据、硬编码绕过多环境、响应提取函数没被用到），这三处正是面试被深挖时会露馅的地方，优先修。**

---

## 1. 你问的红线：为什么 `from core import ...` 会报红

### 1.1 先给结论

**不是代码写错了，也不是缺 `__init__.py`。是"编辑器看代码的角度"和"pytest 跑代码的角度"用了两个不同的根目录。**

四个包 `core/`、`utils/`、`config/`、`testcases/` 全部都有 `__init__.py`，这一点我已经逐个确认过了，包结构本身没问题。

### 1.2 两个"根"的差异

| | 静态分析（IDE 画红线） | 运行时（`python run.py` 跑得通） |
|---|---|---|
| 基准根目录 | 工作区根 `automation-portfolio` | `01-api-test-framework` |
| 谁来定这个根 | 你用 IDE 打开的文件夹 | `run.py:50` 的 `cwd=BASE_DIR` + `python -m` |
| 搜索路径内容 | `automation-portfolio` 一个目录 | `sys.path[0]` 被注入 `01-api-test-framework` |
| 能否找到 `core` | ❌ 找不到（要找的是 `automation-portfolio/core`） | ✅ 找得到（`01-api-test-framework/core`） |
| 结果 | `Unresolved reference 'core'` / `Import "core" could not be resolved` | 正常执行 |

关键点在于 **`python -m` 会把当前工作目录插到 `sys.path[0]`**：

```50:50:01-api-test-framework/run.py
        code = subprocess.call(cmd, cwd=BASE_DIR)
```

`run.py:45-50` 构造的命令是 `[python, "-m", "pytest", "testcases", ...]`，并且显式把 `cwd` 设成了子项目目录。所以运行时 `sys.path` 里有 `01-api-test-framework`，`from core import assertions` 自然成立。

而静态分析器**不执行代码**，它只按"项目根 + 已知搜索路径"去推导。你的项目根是 `automation-portfolio`，它就在那儿找 `core`，找不到 → 画红线。

另外 pytest 自己也有一层保险：`testcases/__init__.py` 存在，pytest 在收集用例时会沿着包结构向上回溯 basedir，把 `01-api-test-framework` 也塞进 `sys.path`。所以就算你不走 `run.py`、直接 `pytest testcases`，大概率也能跑通——**但这条路径依赖 pytest 的内部行为，比 `python -m` 脆弱得多。**

### 1.3 这不是 01 独有的问题，三个项目都一样

跨仓核查的结果：`02-compliant-crawler` 和 `03-rpa-monitor` 用的是完全相同的写法。

```21:21:02-compliant-crawler/main.py
from utils.logger import get_logger
```

```18:18:03-rpa-monitor/main.py
from utils.logger import get_logger
```

```12:12:03-rpa-monitor/run_scheduled.py
from main import load_config, run_once
```

也就是说：**只要你的 IDE 打开的是 `automation-portfolio` 这一层，三个项目的 `core` / `utils` / `config` / `crawler` / `monitor` / `main` 全部会报红。** 这是仓库级结构问题，不是某个文件写错了。

全仓检索 `pythonpath` / `pyrightconfig` / `pyproject` / `setup.py` / `sys.path` / `extraPaths` / `rootdir`，除 `LICENSE` 里 "Co**pyright**" 的误命中外**全部 0 命中**——仓库里从来没有配置过任何搜索路径，红线是必然的。

### 1.4 自查方法（30 秒确认）

在子项目目录下执行，观察 `sys.path[0]`：

```bash
cd 01-api-test-framework
python -c "import sys; print(sys.path[:3])"
python -m pytest --collect-only -q   # 能收集到用例 = 运行时路径 OK
```

如果前者打印的路径里**没有** `01-api-test-framework`，而后者能正常收集用例，那就 100% 印证了上面的结论。

### 1.5 修复方案对比

| 方案 | 做法 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|---|
| **A1. 换项目根**（最省事，推荐先试） | 用 PyCharm 的 `File → Open` 直接打开 `01-api-test-framework` 这个文件夹，而不是打开 `automation-portfolio` | 零配置、零文件改动，红线立刻消失 | 一次只能开一个子项目，跨项目查看要开多个窗口 | 单项目深度开发时 |
| **A2. 标记 Sources Root**（PyCharm 多项目共存，推荐） | 在 `automation-portfolio` 项目里，右键 `01-api-test-framework` → `Mark Directory as` → `Sources Root`（`02`、`03` 同理） | 一个窗口装三个项目，红线全消，符合 PyCharm 的心智模型 | 配置存在 `.idea/` 里，而根 `.gitignore:20` 忽略了 `.idea/` → **clone 后需要重新标记一次**，不随仓库分发 | 你当前这种多子项目仓库 |
| **A3. `pyrightconfig.json`**（VS Code / Pylance / CLI，已落地 ✅） | 仓库根新增配置文件，用 `extraPaths` 把三个子项目根加进搜索路径 | 零代码改动；**能提交进 Git，协作者 clone 下来就生效**；`pyright` CLI 也认 | PyCharm 不读这个文件；对三个项目里同名的 `utils` 包会按 `extraPaths` 顺序优先解析到第一个（静态分析层面轻微失真，不影响运行） | VS Code 用户 / CI 静态检查 / 团队协作 |
| **B. `pytest.ini` 加 `pythonpath`**（运行时加固，建议补） | 在 `pytest.ini` 加一行 `pythonpath = .` | 让运行时**不再依赖 cwd**，在任意目录敲 `pytest` 都能跑；pytest ≥ 7.0 原生支持（`requirements.txt` 已声明 `pytest>=7.0`） | 只治运行时，不治 IDE 红线 | 建议与 A 系列并用，形成"IDE + 运行时"双保险 |
| **C. 打包可编辑安装**（最规范） | 每个子项目加 `pyproject.toml`，`pip install -e .` | IDE 和运行时一次性全通；支持后续改相对导入 | 需要额外的构建配置与安装步骤，和"clone 下来就能跑"的轻量承诺有点冲突；三个项目要分别装 | 长期维护 / 企业级交付 |
| **D. 改成相对导入**（不推荐） | 把 `from core import ...` 改成 `from ..core import ...` | 看起来"规范" | **会直接破坏 pytest 的 rootdir 行为**，单文件调试、直接 `pytest testcases/test_auth.py` 都会炸；收益为负 | 别用 |

### 1.6 本次已经做了什么

已在仓库根新增 **`pyrightconfig.json`**（方案 A3）：把 `01/02/03` 三个子项目根加入 `extraPaths`，顺带 `exclude` 掉 `__pycache__` / `reports` / `logs` 等产物目录，并把 `pythonVersion` 声明为 3.10。

> **如果你用的是 PyCharm，请再补做 A1 或 A2** —— PyCharm 不读 `pyrightconfig.json`，它只认 Sources Root 标记。
> 如果你用的是 VS Code + Pylance，那么**什么都不用做**，重启一下 Pylance（`Ctrl+Shift+P` → `Pylance: Restart Language Server`）红线就会消失。

**没有改动任何一行源码**，这是刻意的：红线是路径问题，不是代码问题，改代码属于用错误的工具解决正确的问题。

---

## 2. 架构评价

### 2.1 分层结构

```
01-api-test-framework/
├── run.py            入口编排：起 Mock → 跑 pytest → 出报告
├── mock_server.py    被测服务（纯标准库，零依赖）
├── conftest.py       夹具层：client / variables / auto_login
├── pytest.ini        pytest 配置
├── config/           配置层：多环境 yaml + loader
├── core/             核心封装层：http_client / assertions / extractor
├── utils/            通用工具层：logger / data_loader
├── data/             数据层：cases.yaml（数据驱动）
├── testcases/        用例层：auth / user / order
└── reports/          产物层（gitignore）
```

**评价：分层是对的，而且分得干净。**

- 依赖方向单向且明确：`testcases → core / utils / config`，核心层不反向依赖用例层，没有任何循环依赖（全仓 import 语句已逐条核查）。
- `core` 和 `utils` 的边界划得准：`core` 放"跟接口测试强相关"的封装（HTTP 客户端、断言库、变量池），`utils` 放"跟业务无关"的通用能力（日志、文件读取）。这是很多初学者会混在一起的地方，你分开了。
- 用例层做到了"只写业务语义"：`test_order.py` 里没有一个 `requests.` 调用，全部走 `client` 夹具——这正是框架化的意义。

### 2.2 夹具设计

`conftest.py:17-49` 三个夹具的分工是合理的：

| 夹具 | 作用域 | 职责 | 评价 |
|---|---|---|---|
| `client` | session | 按 `--env` 造 HTTP 客户端 | ✅ 好：session 级复用 `requests.Session()`，连接复用，性能正确 |
| `variables` | session | 变量池 | ⚠️ 与 `auto_login` 返回同一个对象，语义重复（见 P1-5） |
| `auto_login` | session | 登录 + 准备依赖数据 | ⚠️ 承担了"登录"和"造数据"两件事，且失败路径不友好（见 P1-4） |

`--env` 通过 `pytest_addoption`（`conftest.py:13-14`）注入，是标准做法，比读环境变量更可控。

### 2.3 Mock 服务设计（这是最大的亮点）

`mock_server.py` 用 `http.server` 纯标准库实现，价值被低估了：

- **零第三方依赖**，任何 Python 环境都能起；
- **刻意构造了难以在外网稳定复现的场景**：401 鉴权失败、400 参数缺失、404 资源不存在、500 服务异常、3 秒慢响应（`mock_server.py:76-80`）——这些正是接口测试最需要覆盖、但真实环境最难稳定触发的边角；
- **与"clone 即跑"形成闭环**：`run.py` 自动起停（`run.py:34-38`、`run.py:56-59`），用户不需要任何手工步骤。

这个设计体现的是**交付意识**——你在意别人拿到代码后能不能跑起来，这一点比框架本身更能打动面试官。

---

## 3. 优点清单（可以直接写进简历的部分）

1. **四层分层架构**：`core`（封装）/ `testcases`（用例）/ `data`（数据）/ `config`（配置）职责分离，依赖单向无环。
2. **接口依赖传递**（`conftest.py:38-49`）：登录取 token → 创建用户取 user_id → 下单，用 session 级变量池串起完整业务链路。这是接口自动化最核心的难点，你做出来了。
3. **数据驱动**（`data/cases.yaml` + `testcases/test_auth.py:8-11`）：新增用例只加 yaml，不改代码。
4. **统一断言库**（`core/assertions.py`）：覆盖 HTTP 状态码、业务 code、字段值、字段类型、必填字段、响应耗时六个维度，失败信息可读。
5. **HTTP 客户端封装**（`core/http_client.py`）：Session 复用、token 自动注入、超时控制、指数退避重试（`http_client.py:50` 的 `time.sleep(2 ** i)`）、请求响应日志。
6. **多环境切换**：`pytest --env=dev/test/prod` + 环境变量覆盖（`config/loader.py:17-18`），预留了 CI/CD 接入点。
7. **一键运行**（`run.py`）：自动起服务 → 等端口就绪（`wait_port`）→ 跑用例 → 出 HTML 报告 → 关服务，全生命周期托管。
8. **线程安全变量池**（`core/extractor.py:11-28`）：显式用 `threading.Lock`，说明你考虑过并发执行（pytest-xdist）的场景。

---

## 4. 问题清单

### P0（会导致交付失败，必须修）

#### P0-1 ✅ 已修复 `.gitignore` 会吞掉 `data/cases.yaml`，与"clone 即跑"承诺直接冲突

**位置**：原根 `.gitignore:13`

```
data/
```

**问题**：这条规则会匹配**任意层级**的 `data` 目录，包括 `01-api-test-framework/data/`。而该目录下的 `cases.yaml` 是**源码级的测试数据**，不是运行产物。

**影响**：
- 仓库里根本没有 `cases.yaml`，别人 clone 下来后，`testcases/test_auth.py:8` 和 `testcases/test_user.py:9` 在**用例收集阶段**就会抛 `FileNotFoundError`，整个项目一条用例都跑不起来；
- README 第 3 行、README 第 27 行、以及 `docs/简历与接单话术.md:94` 都承诺了"clone 下来就能跑"——**对外承诺与实际仓库状态不一致**，这是面试官 clone 你仓库时会立刻发现的问题；
- 讽刺的是，02/03 的 `data/`：`02-compliant-crawler/data/` 放的是 `books.csv`、`books.db`，`03-rpa-monitor/data/` 放的是 `monitor.db`，这两个**确实是运行产物，忽略是对的**。也就是说这条规则对 02/03 正确、只对 01 误伤。

**改法**（二选一，推荐 A）：

```gitignore
# A. 精确化：只忽略产物目录，放行 01 的测试数据
/02-compliant-crawler/data/
/03-rpa-monitor/data/
!01-api-test-framework/data/
!01-api-test-framework/data/*

# B. 更干脆：把 01 的数据目录改名为 testdata/，彻底避开 data/ 规则
#    （需同步改 test_auth.py:8、test_user.py:9 两处路径）
```

**补充事实（2026-08-31 核实）**：仓库在本次评审前**从未执行过 `git init`**（根目录无 `.git`），所以 `cases.yaml` 实际上**还没有被真正丢失过**——这个 P0 属于"首次提交前必须修好"的预防性缺陷，而不是已经造成损失的事故。修复已于首次提交前完成，风险已消除。

**验证结果（2026-08-31 实跑）**：

```
> git check-ignore -v 01-api-test-framework/data/cases.yaml
（无输出）                                         ← 不再被忽略 ✅

> git check-ignore -v 02-compliant-crawler/data/books.db 03-rpa-monitor/data/monitor.db
.gitignore:19:/02-compliant-crawler/data/   02-compliant-crawler/data/books.db
.gitignore:20:/03-rpa-monitor/data/         03-rpa-monitor/data/monitor.db   ← 仍被忽略 ✅
```

`git add -A --dry-run` 结果为 58 个文件，其中含 `01-api-test-framework/data/cases.yaml`，且无 `.venv/`、`.idea/`、`__pycache__/`、`.pyc`、`reports/`、`.log` 等任何产物混入。

#### P0-2 ✅ 已修复（配置层）静态分析红线全仓泛化

**位置**：三个子项目的全部跨包 import（`conftest.py:8-10`、`testcases/*.py:2-7`、`core/http_client.py:12` 等）

**问题与影响**：详见第 1 节。红线会让协作者和面试官第一眼觉得"这个项目环境没配好"，而在作品集场景下第一印象的成本很高。

**已落地**：`pyrightconfig.json`（方案 A3）+ `pytest.ini` 的 `pythonpath = .`（方案 B），静态与运行时两侧均已处理。
**仍需你手动做一步**：PyCharm 不读 `pyrightconfig.json`，请补做方案 A1 或 A2（见 1.6）。

---

### P1（设计缺陷 / 亮点与实现不符，建议修）

#### P1-3 用例里硬编码 `BASE_URL`，绕过了 `--env` 多环境机制

**位置**：`testcases/test_user.py:10`、`testcases/test_order.py:5`

```10:10:01-api-test-framework/testcases/test_user.py
BASE_URL = "http://127.0.0.1:8000"
```

**问题**：这两个文件里另外 `new` 了一个客户端（用于验证"未登录访问"），但 base_url 写死，没有走 `client` 夹具的 `--env` 配置。

**影响**：
- 一旦 `pytest --env=test` 指向非 8000 端口的环境，**鉴权类用例全部打到本地 mock**，测的不是目标环境；
- 与 README 第 11 行宣传的"多环境切换，接入真实环境只需改配置"直接矛盾——这是**宣传的卖点没有真正贯通**，面试被追问"你切换 prod 环境时会发生什么"就答不上来。

**改法**：复用 `env` 夹具构造未登录客户端，彻底删掉硬编码常量。

```python
# conftest.py 新增夹具
@pytest.fixture(scope="session")
def unauth_client(env) -> HttpClient:
    """未登录客户端：用于鉴权类负向用例，同样遵守 --env"""
    cfg = load_config(env)
    return HttpClient(base_url=cfg.get("base_url", "http://127.0.0.1:8000"),
                      timeout=cfg.get("timeout", 10))
```

```python
# test_user.py / test_order.py
def test_users_require_auth(unauth_client):
    assertions.assert_status_code(unauth_client.get("/api/users"), 401)
```

#### P1-4 `auto_login` 夹具失败路径脆弱，且一个夹具干了两件事

**位置**：`conftest.py:38-49`

```43:45:01-api-test-framework/conftest.py
    token = resp.json()["data"]["token"]
    client.token = token
    variables.set("token", token)
```

**问题**：
- Mock 服务没起来时，`resp` 是 `ConnectionError`；登录失败时，`resp.json()["data"]` 抛 `KeyError`。两种情况下 pytest 报出的都是一长串 traceback，**看不出真正原因是"服务没起"还是"账号错了"**；
- 因为是 session 级夹具，它一挂，**所有依赖它的用例全部 error**，形成"雪崩"，排查成本高；
- 夹具同时承担"登录"和"创建依赖用户"两件事（`conftest.py:47-48`），违反单一职责，后续要加"准备订单数据"时会继续往里堆。

**改法**：

```python
@pytest.fixture(scope="session")
def auto_login(client, variables):
    login = load_login()
    resp = client.post("/api/login", json=login)

    assert resp.status_code == 200, (
        f"前置登录失败，后续全部用例无法执行。"
        f"请确认 Mock 服务已启动且账号正确 | "
        f"base_url={client.base_url} status={resp.status_code} body={resp.text[:200]}"
    )

    data = resp.json().get("data") or {}
    token = data.get("token")
    assert token, f"登录响应中缺少 token: {resp.text[:200]}"

    client.token = token
    variables.set("token", token)
    return variables
```

顺带把"创建依赖用户"拆成独立夹具 `prepared_user`，让职责可组合。

#### P1-5 `variables` 与 `auto_login` 两个夹具返回同一个对象，语义重复

**位置**：`conftest.py:22-24` 与 `conftest.py:38-49`；用法见 `testcases/test_user.py:37,42`

**问题**：`variables` 返回 `VariablePool()`，`auto_login` 最后 `return variables` —— 两者是**同一个实例**。于是用例里出现了 `auto_login.set(...)` 这种写法：一个叫"自动登录"的东西被用来存变量，读起来很怪，且新人很容易误用成 `variables.set()` 后发现数据在另一个夹具里读不到（其实是同一个，但没人敢确定）。

**改法**：删掉 `variables` 夹具，只保留 `auto_login`（或把它重命名为语义准确的 `context` / `variables`，内部完成登录）。对外只暴露一个名字，消除歧义。

#### P1-6 `extract_variables()` 定义了但全仓无人调用，"响应提取"这个亮点没落地

**位置**：`core/extractor.py:31-47`

**问题**：跨仓符号核查结果——`extract_variables` 只在自己的 docstring（`extractor.py:5-6`）里出现过，**没有任何调用方**。变量池的实际使用是 `conftest.py:45,48` 的手写 `set`/`get`，以及 `testcases/test_user.py:37` 的 `auto_login.set(...)`。

**影响**：这是个**一致性风险**，而不只是"死代码"：

- README 第 8 行写"接口依赖传递……变量池自动流转"；
- `docs/简历与接单话术.md:79` 面试话术明确写"我的框架里 core/extractor.py 就是干这个的"；

如果面试官顺着这句话打开 `extractor.py`，看到的是一个**没人调用的函数**，这个"亮点"当场打折。

**改法**：二选一。
- **A（推荐，成本低、立刻闭环）**：在 `conftest.py` 里真正用上它——

```python
from core.extractor import VariablePool, extract_variables

extracted = extract_variables(resp, {"token": "data.token"})
variables.set("token", extracted["token"])
```

- **B**：如果短期内不打算用，就从 `extractor.py` 里删掉，并把 README / 话术文档里的相关描述改成"变量池手动存取"，**宁可少写，不要写没做到的**。

#### P1-7 `config/loader.py` 重复读取并解析同一份 yaml

**位置**：`config/loader.py:11-26`

```13:14:01-api-test-framework/config/loader.py
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
```

**问题**：`load_config()` 和 `load_login()` 各自 `open()` + `safe_load()` 一遍同一个文件。当前只有 `conftest.py:29,41` 两处调用、且都在 session 级夹具里，实际影响很小；但这是**明确的模式缺陷**，一旦有人把它搬进函数级夹具或用例，就会变成每个用例两次磁盘 IO + 两次 YAML 解析。

**改法**：模块级缓存。

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def _raw_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def load_config(env: str = "dev") -> dict:
    env_cfg = dict(_raw_config().get(env, {}))
    if os.environ.get("BASE_URL"):
        env_cfg["base_url"] = os.environ["BASE_URL"]
    return env_cfg

def load_login() -> dict:
    return dict(_raw_config().get("login", {}))
```

**注意**：`load_config` 和 `load_login` 现在返回的是**原始 dict 的引用**（`load_login` 直接 `return raw.get("login", {})`），调用方一旦修改返回值就会污染缓存、进而污染后续所有环境。改成 `dict(...)` 拷贝，顺手把这个隐患也修掉。

#### P1-8 `HttpClient.request()` 的 headers 合并策略会静默丢弃调用方参数

**位置**：`core/http_client.py:36-37`

```36:37:01-api-test-framework/core/http_client.py
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("headers", self._headers())
```

**问题**：`setdefault` 的语义是"key 不存在才设值"。所以**只要调用方传了 `headers`，`self._headers()` 里的 `Authorization` 就永远不会被注入**——鉴权静默失效，而且不报任何错，用例会以 401 的形式失败，排查方向容易被带偏。

同时还有两个小问题：
- `http_client.py:46` 的重试只捕获 `Timeout` / `ConnectionError`，**不覆盖 5xx**。服务端返回 502/503 时不重试，而"服务端瞬时错误"恰恰是最值得重试的场景；
- `http_client.py:51` 的 `raise last_exc`：当 `retry_times=0`（`attempts=1`）且首次请求抛的是 `Timeout` 之外的异常时，`last_exc` 保持 `None`，会抛出一个莫名奇妙的 `TypeError`。虽然当前配置 `retry_times=1` 掩盖了它，但这是个潜在雷。

**改法**：

```python
def request(self, method: str, path: str, **kwargs):
    url = self.base_url + path
    kwargs.setdefault("timeout", self.timeout)

    # 关键：与调用方 headers 合并，而不是被 setdefault 丢弃
    merged = dict(self.session.headers)
    merged.update(kwargs.pop("headers", {}) or {})
    merged.update(self._headers())       # Authorization 始终注入，优先级最高
    kwargs["headers"] = merged

    attempts = self.retry_times + 1
    for i in range(attempts):
        try:
            resp = self.session.request(method, url, **kwargs)
            logger.info(f"[{method}] {path} -> {resp.status_code} "
                        f"{resp.elapsed.total_seconds() * 1000:.0f}ms")
            # 服务端错误也重试
            if resp.status_code >= 500 and i < attempts - 1:
                logger.warning(f"[{method}] {path} 服务端 {resp.status_code}，"
                               f"第 {i+1}/{attempts} 次重试")
                time.sleep(2 ** i)
                continue
            return resp
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.warning(f"[{method}] {path} 第{i + 1}/{attempts} 次失败: {e}")
            if i >= attempts - 1:
                raise                      # 用 raise 代替 raise last_exc，永不为 None
            time.sleep(2 ** i)
```

#### P1-9 用例之间存在隐式的执行顺序耦合

**位置**：`testcases/test_user.py:24-46`

**问题**：`test_create_user`（数据驱动，多条）在成功分支里 `auto_login.set("user_id", ...)`（`test_user.py:37`），而 `test_get_user_exists` 依赖这个 `user_id`（`test_user.py:42`）。两者靠"文件内从上到下执行"的隐式约定串联。

**影响**：
- `pytest -k test_get_user_exists` 单独跑 → `user_id` 为 `None` → 请求 `/api/users/None` → 失败；
- 上 `pytest-xdist` 分布式执行 → 顺序不保证 → 随机失败；
- 你在 `core/extractor.py:12` 专门写了"线程安全的变量池"，说明你考虑过并发——但顺序耦合会让并发执行直接崩，两者是冲突的。

**改法**：把"创建用户"变成显式夹具依赖，而不是隐式副作用。

```python
@pytest.fixture()
def created_user(client, auto_login) -> dict:
    """每个用例独享一个用户，显式依赖，无顺序耦合"""
    resp = client.post("/api/users", json={"name": "张三", "age": 25})
    assertions.assert_status_code(resp, 200)
    return resp.json()["data"]

def test_get_user_exists(client, auto_login, created_user):
    resp = client.get(f"/api/users/{created_user['id']}")
    assertions.assert_status_code(resp, 200)
    assertions.assert_json_field(resp, "id", expected=created_user["id"])
```

#### P1-10 ✅ 已修复 `pytest.ini` 未声明 `pythonpath`，运行时依赖 cwd

**位置**：原 `pytest.ini:1-6`

**问题**：配置里只有 `testpaths`，没有任何路径声明。运行时能跑通完全靠 `run.py:50` 的 `cwd=BASE_DIR` 兜底。一旦有人在仓库根执行 `pytest`，或者 CI 里工作目录不同，就全挂。

**已落地**（与 1.5 方案 B 一致），当前 `pytest.ini`：

```ini
[pytest]
# pythonpath: 把本目录注入 sys.path，使 `from core import ...` 不再依赖 cwd
#             （pytest >= 7.0 原生支持，requirements.txt 已声明 pytest>=7.0）
#             修复前：只能在 01-api-test-framework 目录下执行 pytest，在仓库根执行会全部 import 失败
pythonpath = .
testpaths = testcases
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -q
filterwarnings =
    ignore::DeprecationWarning
```

---

### P2（打磨项，有余力再改）

| 编号 | 位置 | 问题 | 建议 |
|---|---|---|---|
| P2-11 | `utils/logger.py:5-7` | 模块导入即执行 `LOG_DIR.mkdir(exist_ok=True)`，属于**导入副作用**：任何 import 该模块的行为（包括 IDE 静态索引、单元测试导入）都会在磁盘上建目录 | 把 `mkdir` 挪进 `get_logger()` 内部，加 `parents=True` |
| P2-12 | `utils/data_loader.py:13-15` | `load_json()` 全仓无调用方 | 要么在用例中真正用起来（比如 json 格式的用例数据），要么删掉，保持"每个公开函数都有用" |
| P2-13 | `mock_server.py:30-33, 108-110, 147-148` | 内存态用**类属性**存储，`self.next_user_id += 1` 在 `ThreadingHTTPServer`（`mock_server.py:162`）下**非线程安全**，并发时可能产出重复 id | 改用 `threading.Lock()` 保护自增与写入；顺带加一个 `POST /__reset` 接口，让重复运行不累积脏数据 |
| P2-14 | `run.py:12, 40-42` | 端口 8000 硬编码，被占用时只打印提示后 `return 1`，不降级 | 占用时自动探测下一个可用端口（把 `MOCK_PORT` 换成动态值并透传给 pytest），或至少在提示里给出 `--port` 手工参数 |
| P2-15 ✅ 已修复 | `requirements.txt` / README | 源码用了 `dict \| None`（`http_client.py:19`）等 3.10+ 语法，但**最低 Python 版本从未声明** | 已在 `requirements.txt` 顶部加 `# Requires: Python >= 3.10`，README 新增「环境要求」章节；更规范可再加 `pyproject.toml` 的 `requires-python` |
| P2-16 | `core/assertions.py` 全文 | 断言函数是裸 `assert`，pytest 会重写并给出上下文，但如果脱离 pytest 使用（比如当库被别的脚本调用）会失效 | 可接受现状；若要做得更工程化，可让断言在失败时同时打印响应体（当前只打印字段值，不打印原始响应，排查时还要翻日志） |
| P2-17 ✅ 已修复 | 原 `README.md:73-75` | 文末有 3 行多余空行 | 已清理，并补充了「代码评审」章节链接 |

---

## 5. 重构优先级路线图

| 优先级 | 事项 | 预估工作量 | 投入产出比 | 状态 |
|---|---|---|---|---|
| **第 1 批** | P0-1 修 `.gitignore` 并补提 `cases.yaml` | 5 分钟 | ⭐⭐⭐⭐⭐ | ✅ 已修复并验证通过 |
| **第 1 批** | P0-2 消除红线（`pyrightconfig.json` + `pytest.ini pythonpath`） | 5 分钟 | ⭐⭐⭐⭐⭐ | ✅ 已修复（PyCharm 需补 Sources Root） |
| **第 2 批** | P1-6 让 `extract_variables` 真正被使用 | 15 分钟 | ⭐⭐⭐⭐⭐ | ⬜ 待办（直接守住一个简历亮点） |
| **第 2 批** | P1-3 去掉硬编码 `BASE_URL` | 20 分钟 | ⭐⭐⭐⭐ | ⬜ 待办（守住"多环境"卖点） |
| **第 3 批** | P1-4 / P1-5 重构夹具（友好报错 + 单一职责） | 40 分钟 | ⭐⭐⭐⭐ | ⬜ 待办 |
| **第 3 批** | P1-8 修 `HttpClient` headers 合并 + 5xx 重试 | 30 分钟 | ⭐⭐⭐⭐ | ⬜ 待办 |
| **第 4 批** | P1-7 配置缓存 / P1-9 去顺序耦合 | 1 小时 | ⭐⭐⭐ | ⬜ 待办 |
| **第 5 批** | P2-11 ~ P2-16 打磨 | 1-2 小时 | ⭐⭐ | ⬜ 待办（P2-15 / P2-17 已顺带修复） |

**排序逻辑**：先修"会让别人跑不起来 / 一眼看出问题"的（P0），再修"承诺与实现不一致"的（P1-3、P1-6，这类最伤面试），最后才是纯技术打磨。

---

## 6. 面试时怎么讲这些"已知问题"

主动暴露已知问题、并说清"我为什么这么设计 / 下一步怎么改"，比假装完美更能拿分。下面是可以直接用的话术。

**Q：我看你项目里 IDE 全是红线，环境没配好吗？**
> 这是我有意保留的结构：仓库根放了三个独立子项目，每个子项目自带顶层包。运行时靠 `python -m pytest` 把子项目根注入 `sys.path`，所以跑得通；静态分析器不执行代码，需要 `pyrightconfig.json` 的 `extraPaths` 或 PyCharm 的 Sources Root 来对齐搜索路径。我在仓库里放了配置文件，也写进了评审报告。顺带说一句——**这个坑的本质是"静态分析路径和运行路径必须对齐"，在任何单仓多项目的工程里都会遇到。**

**Q：你的接口依赖是怎么传递的？**
> 用 session 级变量池，`core/extractor.py` 里的 `VariablePool` 是线程安全的（`threading.Lock`），登录拿 token、创建用户拿 user_id，下游用例直接取。我在 `conftest.py` 的 `auto_login` 里串起了完整链路。
> *（注意：说这句之前请先把 P1-6 修掉，否则会被追问到没人调用的函数。）*

**Q：你这个框架有什么已知的不足？**
> 三个，我都记在评审报告里了。一是早期用例里有硬编码 base_url，绕过了 `--env`，我已经在改成复用 `env` 夹具；二是变量池目前是手动存取，`extract_variables` 的按路径提取还没接进主流程；三是部分用例之间有执行顺序耦合，上 xdist 分布式跑会不稳定，我计划用显式夹具依赖替换掉顺序依赖。
> **讲"已知问题 + 改进方案"，比讲"我很完美"更能证明你真的做过工程。**

**Q：多环境怎么切换？**
> `pytest --env=dev/test/prod`，配置在 `config/config.yaml`，还支持 `BASE_URL` 环境变量覆盖，方便 CI 注入。切环境只改配置，用例代码零改动。
> *（这条要等 P1-3 修完才能理直气壮地说，否则对方一问"那为什么 test_user.py 里写死了 127.0.0.1:8000"就尴尬了。）*

---

## 7. 附：本次改动清单

### 7.1 已完成的修复

| 文件 | 操作 | 对应问题 | 说明 |
|---|---|---|---|
| `pyrightconfig.json` | 新增 | P0-2 | 静态分析搜索路径配置（方案 A3），供 VS Code / Pylance / pyright CLI 使用 |
| `.gitignore` | 修改 | P0-1 | 无前缀的 `data/` → 精确匹配 `/02-compliant-crawler/data/`、`/03-rpa-monitor/data/`，放行 01 的测试数据 |
| `01-api-test-framework/pytest.ini` | 修改 | P1-10 | 新增 `pythonpath = .` + `filterwarnings`，运行时不再依赖 cwd |
| `01-api-test-framework/requirements.txt` | 修改 | P2-15 | 声明 `Requires: Python >= 3.10` |
| `01-api-test-framework/README.md` | 修改 | P2-15 / P2-17 | 新增「环境要求」章节、清理文末空行、补充评审报告链接 |
| `docs/code-review-01-api-test-framework.md` | 新增 | — | 本报告 |

**全部为配置与文档层改动，`.py` 源码 0 改动，业务逻辑未受影响。**

### 7.2 需要你手动完成的步骤

**第 1 步：~~确认 `cases.yaml` 已能被 git 追踪~~** ✅ 已于 2026-08-31 验证通过，详见 P0-1 段落的实跑结果。本地仓库已 `git init`，待提交 58 个文件。

**第 2 步：PyCharm 消除红线**（`pyrightconfig.json` 对 PyCharm 无效）

二选一：
- **A1**：`File → Open`，直接把 `01-api-test-framework` 作为项目根打开；
- **A2**（推荐，可同时看三个项目）：在当前 `automation-portfolio` 项目里，右键 `01-api-test-framework` → `Mark Directory as` → `Sources Root`，`02`、`03` 同理。

> 提醒：A2 的配置存在 `.idea/` 里，而 `.gitignore:20` 忽略了 `.idea/`——**clone 到新机器后需要重新标记一次**。这是 PyCharm 的固有行为，无法随仓库分发；`pyrightconfig.json` 的作用正是让用 VS Code / CI 的协作者免掉这一步。

### 7.3 剩余待办

P1-3（硬编码 base_url）、P1-6（`extract_variables` 未被调用）是**投入产出比最高**的两项，合计约 35 分钟，建议优先安排。这两项都直击"宣传卖点没落地"的问题，也是面试最容易被追问的点。
