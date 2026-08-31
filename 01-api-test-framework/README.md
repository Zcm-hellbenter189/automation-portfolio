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

## 快速开始

```bash
# 1. 创建虚拟环境（任选其一）
python -m venv .venv
# Windows 激活
.venv\Scripts\activate
# 2. 安装依赖
pip install -r requirements.txt
# 3. 一键运行（自动启动 Mock 服务并执行全部用例）
python run.py
# 4. 打开测试报告
reports/report.html
```

手工运行（需先启动 mock）：
```bash
python mock_server.py --port 8000
pytest testcases --html=reports/report.html --self-contained-html
```

## 运行效果

```
[*] Mock 服务已启动: http://127.0.0.1:8000
[*] 开始执行测试用例 ...
..............                                      [100%]
[*] pytest 退出码: 0
[*] 测试报告已生成: ...\reports\report.html
```

## 目录结构

```
01-api-test-framework/
├── run.py                 一键运行入口（起 mock → 跑 pytest → 出报告）
├── mock_server.py         本地 Mock 接口服务（纯标准库，零依赖）
├── conftest.py            pytest 夹具：client / variables / auto_login
├── pytest.ini             pytest 配置
├── config/                多环境配置（dev/test/prod）
│   ├── config.yaml
│   └── loader.py
├── core/                  框架核心封装
│   ├── http_client.py     Session 封装：token 注入/超时/重试/日志
│   ├── assertions.py      统一断言库
│   └── extractor.py       响应提取 + 变量池（接口依赖传递）
├── utils/                 日志 / 数据读取
├── data/cases.yaml        数据驱动用例数据
├── testcases/             用例层（auth / user / order 依赖链）
└── reports/               运行产物：HTML 报告、日志（git 忽略）
```

## 简历亮点写法

> 独立设计并实现接口自动化测试框架：基于 Requests + Pytest，支持数据驱动、多环境切换、接口依赖传递（变量池）、统一断言与性能断言；封装 HTTP 客户端实现鉴权注入、超时控制与指数退避重试；集成 pytest-html 报告与一键运行脚本，实现「clone 即跑」，覆盖登录鉴权、CRUD、业务异常、性能等 15+ 用例场景。

## 代码评审

完整的架构评审与问题清单见 [`docs/code-review-01-api-test-framework.md`](../docs/code-review-01-api-test-framework.md)。