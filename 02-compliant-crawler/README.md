# 合规爬虫 · 公开图书榜单采集

> 全链路合规数据采集：**请求 → 解析 → 清洗 → 存储 → Excel 导出**，工业级分层。
> 内置 robots.txt 合规校验、强制限速、遇反爬即停 —— 合规是作品的生命线。

## 功能特性

- **完整链路**：fetcher（请求）→ parser（解析）→ pipeline（清洗/去重）→ storage（存储）→ export（报表）
- **robots.txt 合规校验**：启动前真实拉取并解析目标站点 robots.txt，被禁路径直接拒绝运行
- **强制限速**：单线程串行 + 请求间隔限速（遵守 Crawl-delay 精神），不并发冲击目标站
- **反爬即停**：遇 403/429 立即停止采集，不绕验证码、不换 IP 硬刚
- **断点续爬**：标题去重，重复运行不产生重复数据
- **双存储后端**：CSV（Excel 可直接打开）+ SQLite（可查询分析）
- **成果直观**：一键导出 Excel 报表 + 评分分布统计
- **自带演示站点**：本地 mock 图书榜单页，断网也能完整演示全流程，零合规风险
- **全配置化**：改 `config/settings.yaml` 即可切换目标站点（接单时快速适配新需求）

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 1. 快速验证（本地演示站点，只抓 1 页）
python main.py --limit 1

# 2. 完整抓取（本地演示站点，默认 2 页）
python main.py

# 3. 切换真实目标：豆瓣读书 Top250（需网络，自动限速 3s/请求）
python main.py --source douban

# 4. 导出 Excel 报表
python export_report.py
```

## 运行效果

```
[*] 演示站点已启动: http://127.0.0.1:9000/top250?start=0
INFO | crawler | 未配置 robots.txt（本地演示站点），跳过校验
INFO | crawler | 抓取第 1/1 页: http://127.0.0.1:9000/top250?start=0
INFO | fetcher  | [GET] http://127.0.0.1:9000/top250?start=0 -> 200
INFO | crawler | 采集完成: 共 25 条
INFO | crawler | CSV 输出: ...\data\books.csv
INFO | crawler | SQLite 输出: ...\data\books.db
[*] 演示站点已关闭
```

## 目录结构

```
02-compliant-crawler/
├── main.py                  入口（--source mock|douban, --limit N）
├── export_report.py         导出 Excel 报表 + 评分分布统计
├── config/settings.yaml     目标站点 / 合规参数 / 存储路径（全配置化）
├── crawler/
│   ├── robots_checker.py    robots.txt 合规校验（红线模块）
│   ├── fetcher.py           限速器 + 指数退避重试 + 遇 403/429 即停
│   ├── parser.py            parsel 解析（CSS/XPath 双语法）
│   ├── pipeline.py          字段清洗 + 去重
│   └── storage.py           CSV + SQLite 双存储后端
├── mock_site/               本地演示站点（断网兜底，零合规风险）
├── data/                    运行产物：books.csv / books.db
├── export/                  运行产物：Excel 报表
└── logs/                    运行日志
```

## 合规声明（重要）

本项目严格遵守以下红线，数据仅用于学习演示：

1. 不采集个人隐私数据、账号密码、登录态
2. 强制校验并遵守 robots.txt
3. 请求间隔 ≥3 秒、单线程串行，不并发冲击目标站
4. 遇 403/429/验证码立即停止，不绕过验证码、不更换 IP 硬刚
5. 仅采集公开字段（书名/作者/评分等），不采集受版权保护的长篇内容
6. 数据不商用、不转售、不分发原始数据

> 法律提示：robots.txt 是技术层面的允许性判断，不代表完全免责。商业使用前请阅读目标站点的服务条款并取得授权。

## 简历亮点写法

> 独立实现合规数据采集系统：requests + parsel 完成公开榜单数据采集，全链路覆盖请求限速、指数退避重试、robots.txt 合规校验、字段清洗去重、CSV/SQLite 双存储与 Excel 报表导出；具备「遇反爬即停」的合规意识与「断点续爬」的稳定性设计，可配置化适配不同站点。
