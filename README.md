# 自动化作品集 · Automation Portfolio

> 一个人就是一个团队：用 Python 把「接口测试、数据采集、流程自动化」做到**能交付、能验收、有文档**。

## 我是谁

本人周灿明软件工程专业，专注 Python 自动化方向。擅长把重复的人工操作变成可靠的自动化程序，交付带测试、带文档、带验收标准的结果。

## 技能栈

| 方向 | 技术 |
|---|---|
| 接口自动化 | Python · Requests · Pytest · Allure（可选） |
| UI 自动化 | Selenium · Appium |
| 接口调试/性能 | Apifox · JMeter |
| 数据采集 | Requests · Parsel（CSS/XPath）· 合规限速 |
| 流程自动化 | APScheduler · openpyxl（Excel 报表） |

## 三个作品

| 作品 | 目录 | 一句话 | 核心亮点 |
|---|---|---|---|
| 接口自动化测试框架 | [`01-api-test-framework`](01-api-test-framework/) | 企业级接口自动化框架：数据驱动 + 接口依赖传递 + 一键报告 | 分层架构 / 变量池依赖链 / 多环境切换 |
| 合规爬虫 | [`02-compliant-crawler`](02-compliant-crawler/) | 全链路合规数据采集：请求→解析→清洗→存储→Excel 导出 | robots.txt 校验 / 限速 / 双存储 / 断点续爬 |
| RPA 定时监控 | [`03-rpa-monitor`](03-rpa-monitor/) | 定时采集 + Excel 报表 + 异常告警的自动化闭环 | APScheduler / 环比分析 / 告警分级 |

每个作品都**自带本地 Mock 数据源**，clone 下来即可运行，不需要外网、不需要付费服务。

## 快速开始

```bash
# 1. 进入任意作品目录，创建虚拟环境并安装依赖
cd 01-api-test-framework
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt

# 2. 一键运行
python run.py
```

各作品独立运行，详见各自 README。

## 合规承诺

所有数据采集项目严格遵守：robots.txt 校验、强制限速、不碰隐私数据、不绕过反爬、数据仅用于学习演示。详见各项目 README 的合规声明。

## 联系方式

微信 hellbenter189 / GitHub Zcm-hellbenter189
