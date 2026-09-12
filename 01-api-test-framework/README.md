# 接口自动化测试框架

> 企业级接口自动化测试框架：**数据驱动 + 接口依赖传递 + 一键报告**。clone 即可运行，无需外网、无需付费服务。

## 功能特性

- **分层架构**：`core`（封装）/ `testcases`（用例）/ `data`（数据）/ `config`（配置）四层分离，工程化规范
- **接口依赖传递**：登录取 token → 创建用户取 id → 下单，变量池自动流转（接口自动化的核心难点）
- **数据驱动**：yaml 管理用例数据，一条数据一个用例，新增用例不写代码
- **统一断言库**：HTTP 状态码 + 业务 code + JSON 字段 + 字段类型 + 响应耗时，全维度校验
- **多环境切换**：`pytest --env=dev/test/prod` 一键切换，接入真实环境只需改配置
- **失败重试 + 超时控制**：网络抖动自动指数退避重试，不误报
- **自带 Mock 服务**：纯标准库实现，任何环境 clone 下来即可跑通
- **一键运行**：`python run.py` 自动起服务、跑用例、出 HTML 报告

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
setx PYTHONUTF8 1
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

## 快速开始

```bash
# 1. 创建虚拟环境（任选其一）
python -m venv .venv
# Windows 激活
.venv\Scripts\activate
# 2. 安装依赖
pip install -r requirements.txt
# 3. 【最常用】一键全跑（自动起 mock、跑用例、出报告）
python run.py
# 手工跑（需先开 mock）
python mock_server.py --port 8000     # 终端 A
pytest -m "not slow"                  # 终端 B：跳过慢用例，日常提速
pytest -m slow                        # 只跑慢用例
pytest testcases/test_auth.py         # 只跑单个文件
pytest testcases/test_auth.py -k "login"   # 按名称过滤
pytest --env=test                     # 切换环境
pytest -v                             # 看每条用例名
pytest --collect-only -q              # 只收集不执行（查用例总数）

# 自定义端口（被占用时 run.py 也会自动换）
python run.py --port 9000

跑完看两处：终端底部「测试结果摘要」（通过率）、`reports/report.html`（逐条明细）。
# 4. 打开测试报告
reports/report.html
```

## 运行效果

```
[*] Mock 服务已启动: http://127.0.0.1:8000
[*] 开始执行测试用例 ...
..............                                      [100%]
[*] pytest 退出码: 0
[*] 测试报告已生成: ...\reports\report.html
```

## 持续集成（CI）

把「手动跑用例」升级为「持续测试」：仓库自带 `Jenkinsfile`，定时自动执行全量用例并产出报告。

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

> 完整接入步骤（装 Jenkins → 装插件 → 配 Allure → 建任务 → 排错 → 面试话术）见 [`docs/jenkins-ci-guide.md`](../docs/jenkins-ci-guide.md)。

## 目录结构

```
01-api-test-framework/
├── run.py                 一键运行入口（起 mock → 跑 pytest → 出报告，支持 --ci）
├── Jenkinsfile            CI 流水线定义（拉代码 → 装依赖 → 执行用例 → 归档报告）
├── mock_server.py         本地 Mock 接口服务（纯标准库，零依赖）
├── conftest.py            pytest 夹具：client / variables / auto_login
├── pytest.ini             pytest 配置
├── requirements.txt       依赖声明（版本下限；含中文注释，必须保持 UTF-8 BOM）
├── requirements.lock.txt  依赖锁文件（确切版本，CI 用它复现环境；纯 ASCII 注释）
├── config/                多环境配置（dev/test/prod）
│   ├── config.yaml
│   └── loader.py
├── core/                  框架核心封装
│   ├── http_client.py     Session 封装：token 注入/超时/重试/日志
│   ├── assertions.py      统一断言库
│   └── extractor.py       响应提取 + 变量池（接口依赖传递）
├── utils/                 日志 / 数据读取
├── data/cases.yaml        数据驱动用例数据
├── testcases/             用例层（auth / register / user / order 依赖链）
└── reports/               运行产物：HTML / JUnit XML / Allure 结果（git 忽略）
```

## 简历亮点写法

> 独立设计并实现接口自动化测试框架：基于 Requests + Pytest，支持数据驱动、多环境切换、接口依赖传递（变量池）、统一断言与性能断言；封装 HTTP 客户端实现鉴权注入、超时控制与指数退避重试；集成 pytest-html 报告与一键运行脚本，实现「clone 即跑」，覆盖登录鉴权、CRUD、业务异常、性能等 15+ 用例场景。
>
> **持续集成实践**：基于 Declarative Pipeline 搭建 Jenkins 流水线，实现「拉代码 → 装依赖 → 执行全量用例 → 归档报告」自动化，支持定时与提交触发；集成 Allure + JUnit 双报告体系并保留历史通过率趋势；通过退出码传递保证「用例失败即构建失败」，慢用例用 pytest marker 隔离实现日常/CI 执行策略分离。
