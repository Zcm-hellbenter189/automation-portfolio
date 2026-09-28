# Jenkins 持续集成接入指南（01-api-test-framework）

> 目标：把「手动敲 `python run.py`」升级为「定时自动跑 + 报告可视化 + 失败主动通知」。
> 读完本文你应该能：独立在 Windows 上搭好 Jenkins，跑通本项目的接口自动化流水线，并理解每一个决策背后的取舍。

---

## 一、30 秒看懂 CI / Jenkins

| 概念 | 人话 |
|---|---|
| **CI**（持续集成） | 代码一改就自动跑测试，立刻发现有没有搞坏东西 |
| **CD**（持续交付） | 测试过了自动打包/部署（本项目只做 CI 部分） |
| **Jenkins** | 一个开源的 CI 服务器（Java 写的 Web 应用），本质是「**调度器 + 看板**」 |
| 关键认知 | Jenkins **自己不会测试**，它只负责按时机触发、执行你给的命令、收集产物、展示结果 |

**手动 vs 自动**：

```
手动：你 → 打开 PyCharm → python run.py → 看结果 → 关掉
      （只有你在、想起来才跑；忘了跑没人知道；历史结果无处追溯）

自动：凌晨 2:00 Jenkins 自动 → git pull → pip install → python run.py --ci
      → 记录 20 通过 / 0 失败 → 渲染 Allure 报告 → 失败发通知
```

---

## 二、本项目的流水线长什么样

| 阶段 | 执行命令 | 产出 |
|---|---|---|
| 拉取代码 | `git rev-parse --short HEAD` | 本次构建对应的 commit 号 |
| 准备环境 | `pip install -r requirements.txt` | 依赖就绪 |
| 接口自动化测试 | `python run.py --env=test --ci` | `reports/junit.xml`、`reports/allure-results`、`reports/report.html` |

`run.py` 在这条链路里做的事：

```
起 Mock 服务（自动探测空闲端口） → 透传 BASE_URL → 跑 pytest
  → 清空上轮 allure-results → 产出 JUnit XML + Allure 结果 → 返回 pytest 退出码
```

> **退出码就是构建状态**：`run.py` 直接返回 pytest 退出码，非 0 时 Jenkins 阶段自动变红。
> 这是持续集成的核心约定——**测试失败必须让流水线失败**，否则报告就是摆设。

---

## 三、第一步：先在本地跑通（不装 Jenkins）

先确认现有能力没被破坏，再上 Jenkins：

```powershell
Set-Location "e:\ruanjian\Learn\WorkBuddy\automation-portfolio\01-api-test-framework"

# 1) 回归：原有行为必须保持不变（跑全量用例 + HTML 报告）
& ..\.venv\Scripts\python.exe run.py

# 2) 只跑非慢用例（日常提速）
& ..\.venv\Scripts\python.exe run.py -m "not slow"

# 3) CI 模式：产出 JUnit XML + Allure 结果
& ..\.venv\Scripts\python.exe -m pip install allure-pytest
& ..\.venv\Scripts\python.exe run.py --env=test --ci
```

跑完检查三个目录：

| 路径 | 用途 |
|---|---|
| `reports/report.html` | pytest-html 报告，浏览器直接打开 |
| `reports/junit.xml` | Jenkins `junit` 步骤读取，画通过率趋势 |
| `reports/allure-results/` | Allure 原始数据，本地无 allure 命令行时它只是数据 |

**本地看 Allure 报告（可选）**：下载 `allure-2.x.zip` 解压，把 `bin` 加入 PATH（需 Java 11+），然后：

```powershell
allure serve reports/allure-results     # 临时起个服务直接看
```

> 注意：`run.py` 已经会自动检测 `allure` 命令行，有就渲染，没有就跳过并提示，**不会报错**。

---

## 四、第二步：装 Jenkins（Windows）

### 方式 A：War 包（最省事，推荐先用这个）

1. 装 **Java 17**（Jenkins 新版要求 Java 11/17/21）。
2. 下载 `jenkins.war`：https://www.jenkins.io/download/ （LTS 版）
3. 启动：

```powershell
java -jar jenkins.war --httpPort=8080
```

4. 浏览器打开 `http://localhost:8080`，按提示输入初始密码（见 `%USERPROFILE%\.jenkins\secrets\initialAdminPassword`），选「安装推荐的插件」。

### 方式 B：Docker（有 Docker 时更干净）

```powershell
docker run -d --name jenkins -p 8080:8080 -p 50000:50000 ^
  -v jenkins_home:/var/jenkins_home jenkins/jenkins:lts
```

> ⚠️ Docker 方式下 Jenkins 在容器里，**访问不到宿主机的 `127.0.0.1:8000`**，
> 会导致 Mock 服务和用例连不上。学习阶段请用方式 A（本机直装）。

---

## 五、第三步：装以下插件

**Manage Jenkins → Plugins → Available plugins**，搜索安装：

| 插件 | 必需性 | 用途 |
|---|---|---|
| Git | 默认自带 | 从 Git 仓库拉代码 |
| Pipeline | 默认自带 | 支持 Jenkinsfile |
| **Allure Jenkins Plugin** | **必需** | 渲染 Allure 报告（不装 `allure` 步骤会报错） |
| Timestamper | 推荐 | 日志加时间戳（`timestamps()` 需要它） |
| Email Extension Plugin | 可选 | 失败邮件通知 |
| Workspace Cleanup | 可选 | 构建前清理工作区 |

装完**重启 Jenkins**。

---

## 六、第四步：配置 Allure 命令行工具

**Manage Jenkins → Tools → Allure Commandline**：

1. Name 填 `allure`（和 Jenkinsfile 里的 `jdk: ''` / 默认配置对应，一般留空即可自动选）
2. 勾选 **Install automatically** → 从 Maven Central 选最新版本
3. 保存

> Allure 需要 Java。插件会自己下载 allure 命令行，不用你手动装。

---

## 七、第五步：新建 Pipeline 任务

1. **New Item** → 名字如 `api-test-nightly` → 类型选 **Pipeline** → OK
2. **Pipeline** 区域：
   - Definition：**Pipeline script from SCM**
   - SCM：**Git**
   - Repository URL：你的 GitHub 仓库地址
   - Credentials：添加 GitHub 用户名 + Personal Access Token（私有仓库必需）
   - Branch Specifier：`*/main`
   - **Script Path**：`01-api-test-framework/Jenkinsfile`
3. 保存

> **关键坑：Windows 服务的 PATH**。若 Jenkins 是以 Windows 服务方式安装的，
> 它跑在另一个用户会话下，可能找不到 `python` 命令。
>
> **本项目已用「配置即代码」解决了它**：Jenkinsfile 的 `environment` 块里定义了 `PYTHON` **绝对路径**，
> 所有步骤都用 `"%PYTHON%"` 调用（**不依赖节点的 PATH**）。
> ⇒ 这与「坑 6」（界面里改坏全局 `PATH` 导致 `cmd` 都找不到）是同一条教训的两种解法 ——
> **把路径写进 Jenkinsfile，可 review、可追溯、换节点只改一处。**

---

## 八、第六步：触发方式三选一

| 方式 | 配置 | 适用 |
|---|---|---|
| **手动** | 任务页点「Build Now」 | 第一次验证，必须先用这个跑通 |
| **定时** | Jenkinsfile 里已有 `cron('H 2 * * *')` | 冒烟/巡检场景，最实用 |
| **提交触发（SCM 轮询）** ⭐ | Jenkinsfile 里已有 `pollSCM('H/15 * * * *')` | **本项目实际采用**：每约 15 分钟轮询一次 Gitee，有变更就构建 |
| **Webhook 回调** | 仓库 Settings → Webhooks → `<jenkins地址>/github-webhook/` | ⚠️ **本项目不可用**：Jenkins 跑在本机、无公网可达地址，仓库的回调请求打不进来 |

> ⚠️ **pollSCM 只轮询【任务里配置的那一个仓库 URL】** —— 本项目 Jenkins 从 **Gitee** 拉代码，
> 所以**只推 GitHub 等于没推**，Jenkins 看不到变化。⇒ 推送必须两边都做（本项目用 `git pushall` 别名）。

> `H 2 * * *` 里的 `H` 是 Jenkins 特有的「散列」写法：把执行时刻随机分散到 2 点这一小时内的某分钟，
> 避免多个任务在整点抢资源。写成 `0 2 * * *` 就是硬编码 2:00 整。

---

## 九、第七步：看报告

跑完一次构建后，任务页会出现两个入口：

| 入口 | 内容 | 实际价值 |
|---|---|---|
| **Test Result**（junit） | 用例总数/失败数、历史通过率曲线、失败用例堆栈 | 持续跟踪质量趋势 |
| **Allure Report** | 按 Feature/Story 分组、失败截图与请求响应、重跑历史 | 报告可交付、能定位问题 |

**Allure 比 JUnit 强在哪**：JUnit 只给「哪条挂了」，Allure 能给「请求参数、响应体、断言失败对比、历史趋势」，定位效率完全不同。

---

## 十、第八步：失败通知（可选）

### 邮件（需 Email Extension Plugin）

先在 **Manage Jenkins → System → Extended E-mail Notification** 配好 SMTP，再在 Jenkinsfile 的 `failure` 块里启用：

```groovy
failure {
    emailext to: 'you@example.com',
             subject: "接口自动化失败: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
             body: "构建地址: ${env.BUILD_URL}\n请查看 Allure 报告中的失败用例。"
}
```

### 企业微信机器人（推荐 · 本项目已实现）

**① 拿到 Webhook key**

1. 企业微信 → 进入一个**群聊** → 右上角「…」→ **消息推送** → 添加消息推送

2. 复制它的 **Webhook 地址**，形如：
   `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`（UUID 格式，32 位十六进制）
   **`key=` 后面那一串**就是 `WECOM_WEBHOOK_KEY`
3. ⚠️ 这个 key 等于「往群里发消息的权限」，**绝不要提交到仓库**

> 没有企业微信？可以先免费注册一个企业（个人也能注册）；或用钉钉/飞书机器人，思路完全一致。

**② 把 key 注入 Jenkins**（二选一）

| 方式 | 做法 | 评价 |
|---|---|---|
| **全局环境变量** | Manage Jenkins → System → Global properties → Environment variables → 新增 `WECOM_WEBHOOK_KEY` | ✅ 最快，适合先跑通 |
| **凭据（更安全）** | Manage Jenkins → Credentials → 新增 **Secret text**（ID 如 `wecom-webhook-key`），Jenkinsfile 里用 `withCredentials` 注入 | ✅ 加密存储，不进配置明文 |

**⚠️ 凭据「不会自动变成环境变量」，必须显式绑定 —— 这是它和全局环境变量最大的区别**

| 任务类型 | 绑定方式 |
|---|---|
| **全局环境变量**（方式 A） | **不需要绑定** —— 所有任务自动生效（这也是"最快"的原因） |
| **Pipeline** | 写在 Jenkinsfile 里：`withCredentials([string(credentialsId: 'wecom-webhook-key', variable: 'WECOM_WEBHOOK_KEY')]) { ... }` |
| **Freestyle** | ⚠️ 没有 `withCredentials` 这种东西，要去 **任务配置 → 构建环境 → 勾选「Use secret text(s) or file(s)」→ 增加 → Secret text**，然后填：<br>　Variable = `WECOM_WEBHOOK_KEY`（**必须与脚本读的名字完全一致**）<br>　Credentials = 选那个 `wecom-webhook-key` |

> **只创建凭据、不做绑定 → `notify.py` 会打印「未配置 WECOM_WEBHOOK_KEY，跳过企业微信通知」。**
> （Freestyle 的绑定功能来自 **Credentials Binding Plugin**，通常默认已装）

**⚠️ 两个必踩的坑**：

1. **凭据类型必须选 `Secret text`，不能选 `Secret file`** —— Secret file 会**把内容写成一个临时文件**，环境变量里放的是**文件路径**；脚本拿到路径字符串去调企业微信接口，必然失败（而日志看起来"配了 key 却不生效"，很难查）。
2. **用 `Secret text` 时别自己加引号** —— 有的工具习惯性把值写成 `"xxx"`，引号会被当成 key 的一部分发出去。

**怎么判断到底是哪一步出问题 —— 看构建日志**：

| 日志内容 | 说明 | 修法 |
|---|---|---|
| `未配置 WECOM_WEBHOOK_KEY，跳过企业微信通知` | **key 根本没注入**（没绑定 / Variable 名不一致） | 检查绑定步骤 |
| `ERROR: Could not find credentials ...` | **凭据 ID 不存在** | 回 Credentials 页确认 ID（大小写、连字符） |
| `企业微信返回业务错误: {'errcode': 93000}` | **key 注入成功但值无效** | 检查凭据内容（漏字符 / 带空格） |
| `企业微信通知已发送` | ✅ 通了 | —— |

> **❓ 在 Pipeline 任务里找不到「Use secret text(s) or file(s)」？—— 因为那是 Freestyle 专属的选项。**
>
> **Pipeline 任务的配置页只有「流水线」一栏，根本没有「构建环境」** —— 凭据不在界面上配，而在 **Jenkinsfile 代码里**配。
> 这是两类任务的哲学差异：**Freestyle = 表单式配置（在界面勾选）**；**Pipeline = 代码即配置（在 Jenkinsfile 里声明）**。
>
> ⇒ 用 Pipeline 时**界面上什么都不用配**，只要保证「凭据存在 + ID 与 `credentialsId` 完全一致」，`withCredentials` 就会自己去取。
> ⇒ **若 ID 对不上**，构建会报 `ERROR: Credentials 'xxx' is missing`。
>
> ⚠️ 想"手动验证凭据能否取到"时，**别去改主流水线**（`withCredentials` 只在 `failure` 块里，只有构建失败才会执行）——
> 用一个独立的 Freestyle 临时任务来验最干净。

### 验证「失败通知」的推荐姿势：Jenkins **Replay**（不改仓库、不改配置）

`failure` 块平时不执行（因为用例通常是绿的），想验证它有两个思路：

| 思路 | 做法 | 评价 |
|---|---|---|
| **A. Replay 改触发条件** | 构建页 → 左侧「Replay」→ 编辑器里把 `failure {` 改成别的条件 → Run | ✅ 一行改动，**结果仍是 SUCCESS** |
| **B. Replay 改到失败** | 把 `run.py ...` 那行换成 `exit 1`，让构建真的变红 | ✅ 走的是**真实 failure 路径**；⚠️ 但 `always` 里的 Allure 步骤可能因缺报告报错 |

**⚠️ 思路 A 有一个必踩的坑：`post` 块里「条件名不能重复」**

直觉是"把 `failure` 改成 `always`" —— **但如果文件里已经有 `always { }`（本项目的报告归档就在里面），会直接编译失败**：

```
Duplicate build condition name: "always" @ line 106.
     post {
```

**⇒ 正确改法：把 `failure {` 改成 `success {`**
当前构建是**成功的** → `success` 块正好会被触发；且 `success` **未被占用**，不会冲突。

> `post` 各条件的执行顺序是**固定**的：
> `always → changed → fixed → regression → aborted → failure → success → unstable → cleanup`
>
> 注意：**一张 `post` 块里，每种条件最多出现一次**（这是 Declarative Pipeline 的结构约束，不是 Groovy 的语法约束）。

**Replay 的注意点**：

- Replay 出来的构建**结果仍是 SUCCESS**（`success`/`always` 不改变构建结果），但**通知会真实发出去** ✅
- 消息文案写着"接口自动化测试失败"（`notify.py` 里硬编码）—— 此时你验的是**通道通不通**，不是文案准不准 ✅
- Replay 的改动**只存在于这一次运行**，不写仓库、不改配置、可反复试 ✅

**③ Jenkinsfile 的 `failure` 块**（本项目已写好 —— **含凭据绑定**）

```groovy
failure {
    echo 'API tests failed, check the Allure report for details'

    dir('01-api-test-framework') {
        // ⚠️ 凭据 ID 必须与你在 Jenkins 里创建的 Secret text 凭据一致
        withCredentials([string(credentialsId: 'wecom-webhook-key', variable: 'WECOM_WEBHOOK_KEY')]) {
            bat '"%PYTHON%" scripts/notify.py'
        }
    }
}
```

> ⚠️ **两层 vs 三层**：只写 `dir { bat }` 时，脚本只能读到**全局环境变量**里的 key；
> 要用**凭据**（更安全、推荐长期用），必须补上 `withCredentials` 这一层。
> 缺了它 + 没建凭据二者之一，都会让通知发不出去（前者静默跳过、后者直接报 `CredentialNotFoundException`）。

**④ `scripts/notify.py` 的三个设计点（值得理解，也是可讲的点）**

1. **key 只从环境变量读** —— 凭据不进代码库，换 key 不用改代码；
2. **通知失败不影响构建** —— 异常一律吞掉只打 warning。**通知是锦上添花，不该让流水线「更红」**（构建已经失败，再抛异常只会污染日志、掩盖真正的失败原因）；
3. **没配 key 时静默跳过** —— 本地手动跑也不报错。

> **为什么不直接在 Jenkinsfile 里 curl**：Windows 批处理下 JSON 转义极其易错（`\\"` 层层嵌套，见坑 8 同源问题）；
> 用 Python 写既干净，又顺便多一个实践点。

**本地自测**（不配 key 也应正常退出）：

```bat
..\.venv\Scripts\python.exe scripts\notify.py
# 输出：未配置 WECOM_WEBHOOK_KEY，跳过企业微信通知（退出码 0）
```

---

## 十一、排错手册

| 现象 | 原因 | 解决 |
|---|---|---|
| `allure` 步骤报错 `No such DSL method` | 缺 Allure 插件 | 装 Allure Jenkins Plugin 并重启 |
| `junit` 步骤报错找不到文件 | 上一阶段就崩了，没产出 XML | 已加 `allowEmptyResults: true`；重点看控制台日志 |
| 日志/报告中文乱码 | Windows 控制台默认 GBK | Jenkinsfile 已设 `PYTHONIOENCODING=utf-8` |
| `python: 不是内部或外部命令` | Jenkins 服务用户 PATH 没有 Python | **本项目已解决**：Jenkinsfile 用 `environment.PYTHON` 绝对路径 + `"%PYTHON%"` 调用，不依赖节点 PATH；自定义时照此模式改 |
| `Connection refused` / 全部用例连接失败 | Mock 服务没起来，或端口被占 | `run.py` 已自动探测空闲端口；查日志里打印的实际端口 |
| Allure 报告用例数对不上 | 上轮结果没清导致累积 | `run.py` 已每轮清空 `allure-results`（除非手动加 `--no-clean`） |
| 构建永远绿 | 没让测试失败影响退出码 | 本项目 `run.py` 已直接返回 pytest 退出码 |
| 定时任务不触发 | Jenkins 主节点时区/`H` 散列 | 先用手动 Build Now 验证链路，再调 cron |

### 实战踩坑记录（本项目真实经历 · 2026-09-25 从 0 到跑通）

> 以下都是**实际遇到并解决的**，按发生顺序排列。每条给「现象 → 根因 → 解决」——
> 比"照着文档配一遍"更接近真实工程，也是最有价值的部分。

| # | 现象 | 根因 | 解决 |
|---|---|---|---|
| 1 | `couldn't find remote ref refs/heads/master` | Git 插件默认分支规则是 `*/master`，而仓库默认分支已是 `main`（Git 2.28 起改名，GitHub 亦然） | Branch Specifier 改为 `*/main`（或留空） |
| 2 | `references a local directory, which may be insecure` | Repository URL 被改成本地目录 → Jenkins 安全策略默认禁止本地 checkout。**且本地路径同样只能拿到"已提交"的代码**，省不掉 commit | 改回远程仓库地址。**"从版本库拉代码"是 CI 的本质** |
| 3 | `Recv failure: Connection was reset` | 国内直连 GitHub 被重置（非配置问题） | **代码双推 GitHub + Gitee，Jenkins 改拉 Gitee**（国内直连、零代理） |
| 4 | Gitee 推送 `Incorrect username or password (access token)` | 开了两步验证的账号，git 推送需用**私人令牌**，不能用登录密码 | Gitee「设置 → 安全设置 → 私人令牌」生成（勾 `projects`）后当密码填 |
| 5 | `git config alias.xxx '...'` 报 `error: no action specified` | **PowerShell 向原生程序传参的引号规则与 cmd 不同**，整串命令被拆散 | 复杂配置**直接编辑 `.gitconfig` 文件**，别依赖命令行写入 |
| 6 | `'cmd' 不是内部或外部命令`（所有 `bat` 步骤失效） | Jenkins 全局环境变量 `PATH` **覆盖**（而非追加）了系统路径，丢了 `C:\Windows\System32` | ① 删掉该 PATH；② **更根本：改用 Jenkinsfile 的 `environment` + 绝对路径，不依赖节点全局变量**（配置即代码） |
| 7 | Allure 报 `JAVA_HOME is not set`、`exit code 9009` | `JAVA_HOME` 未配 / 被配成畸形值 | 在 Jenkins 全局属性里设 `JAVA_HOME=<JDK 路径>` |
| 8 | `bat` 里 `${PYTHON}` 不生效 | **Groovy 单引号字符串不做插值**（双引号才插值） | 单引号里用批处理语法 `"%PYTHON%"`；双引号里用 `"${PYTHON}"`。**别混用** |
| 9 | `Could not open requirements file: No such file or directory` | Jenkins 默认工作目录是**仓库根**，项目代码却在 `01-api-test-framework/` 子目录 | 用 **`dir('01-api-test-framework') { ... }`** 包裹（**不能 `cd`**：`bat` 每次都是新 shell）。`post` 阶段的 `reports/*` 路径同理 |
| 10 | 控制台中文乱码（如 `鎺ュ彛鑷姩鍖栨祴璇曟鏋�`） | 两端编码不一致：Python 按 UTF-8 输出，Jenkins 控制台按 GBK 解码 | stage 名改英文（已解决）；`run.py` 的 print 输出可给 Jenkins 加 `-Dfile.encoding=UTF-8` |

**从这 10 个坑提炼的 3 条通用判断**：

1. **"本地能跑、CI 跑不通" → 先查三样**：**工作目录**（相对路径以谁为基准）、**环境变量**（服务账号是否继承）、**依赖来源**（用的是哪个解释器）。
2. **优先"配置即代码"**：路径与环境变量写进 `Jenkinsfile`，而不是 Jenkins 界面。可 review、可追溯、换节点不失效 —— 坑 6 就是"界面配置搞坏全局变量"的典型。
3. **失败要分层定位，别逐个修表象**：坑 6 里 `cmd`、`java`、`python` 三个"找不到"，根因是同一个 **PATH 被覆盖**。

### 实战踩坑记录 · 第二批：失败通知与提交（2026-09-27）

> 第一批（坑 1~10）是"**把流水线跑起来**"；这批是"**让它失败时会通知、并把改动安全提交**"。
> 从坑的数量上看，**"加一个通知"比"搭整条流水线"还容易翻车** —— 因为它牵出了**凭据体系**、**Pipeline 结构约束**、**验证手法**三块新东西。

| # | 现象 | 根因 | 解决 |
|---|---|---|---|
| 11 | 凭据建好了，构建日志却打「未配置 `WECOM_WEBHOOK_KEY`，跳过企业微信通知」 | **凭据 ≠ 环境变量**。凭据是**加密存储**的，"存进去"和"用起来"是两件事，**它不会自动注入到任何变量里** | **必须显式绑定**：Pipeline → Jenkinsfile 里的 `withCredentials([string(credentialsId:..., variable:...)])`；**Freestyle → 任务配置 → 构建环境 → ☑ `Use secret text(s) or file(s)`** |
| 12 | 在 **Pipeline 任务**的配置页里怎么也找不到 `Use secret text(s) or file(s)` | **那是 Freestyle 专属选项**。Pipeline 任务的配置页只有「流水线」一栏，**根本没有「构建环境」** | 分清两类任务的哲学：**Freestyle = 表单式配置（界面勾选）**；**Pipeline = 代码即配置（Jenkinsfile 里声明）**。Pipeline 只要保证「**凭据存在 + ID 与 `credentialsId` 完全一致**」，界面上什么都不用配 |
| 13 | 凭据配好了，**却测不出它到底生效没有**（删了全局变量才露馅） | **全局环境变量在"兜底"** —— 两套机制并存时，**弱的那套被强的那套掩盖**，你看到的成功是别人的功劳 | 验证某一机制前，**先把其他来源全部关掉**。测凭据就先删全局变量；测绑定就先别设默认值 |
| 14 | Jenkinsfile 改完，**整个 pipeline 起不来**（不是"那一步失败"，是压根没开始跑） | `dir { }` 嵌 `withCredentials { }` —— 开了 **2** 个花括号，只闭了 **1** 个，**括号不配平** | **Declarative Pipeline 在「解析期」校验结构**：语法错**不会等到执行那一步才报**，而是整个 pipeline 拒绝启动。**改这类嵌套块后务必数一遍括号**（缩进错位往往是漏括号的信号） |
| 15 | `git commit`（不带 `-m`）报 `E:/.../Microsoft: No such file or directory` | `core.editor` 的值是 `E:/.../Microsoft VS Code/bin/code --wait` —— **路径含空格却没加引号**，Git 在空格处把命令**拆断**了 | ① **省事**：直接用 `-m`（根本不启动编辑器）；② **根治**：`git config --global core.editor "'E:/.../code' --wait"`（**单引号包住整条路径**，`--wait` 留在引号外）。⚠️ `--wait` 不能删：否则编辑器立刻返回，Git 拿到**空 message** |
| 16 | Replay 验证时编译失败：`Duplicate build condition name: "always"` | 文件里**本来就有** `always { }`（报告归档），又把 `failure` 改成 `always` —— **`post` 块里每种条件名最多出现一次** | 改成 **`success {`**：当前构建是成功的 ⇒ 会触发；且 `success` 未被占用。**记住 `post` 条件的固定顺序**：`always → changed → fixed → regression → aborted → failure → success → unstable → cleanup` |
| 17 | 提交后才想起：「文档示例里会不会写进了真 key？」 | 凭据类文档**极易无意中把示例写成真实值**（复制粘贴时手滑） | **提交前扫一遍**：`Select-String -Path <待提交文件> -Pattern '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'`。**示例一律用纯占位符**（本项目已在 `jenkins-ci-guide.md` 命中过一次） |

**第二批提炼的 3 条通用判断**：

1. **安全机制默认「不主动」** —— 凭据不会自动变成环境变量，密钥不会自动注入进程。
   **凡"更安全"的方案，都要求你显式接一根线**；而"更方便"的方案（全局环境变量）恰恰是**自动生效**的。
   ⇒ **方便与安全在这里正好是反的**，这不是巧合：**自动生效本身就意味着"任何人都能拿到"**。
2. **结构约束在「运行前」校验，不给你运行时才发现的机会** —— `post` 条件唯一、括号配平、`credentialsId` 必须存在……
   这些要么在**解析期**直接拒绝启动，要么在**取凭据时**立刻报错。
   ⇒ 好处是"早失败"，代价是**改 Jenkinsfile 后必须真跑一次** —— **静态读一遍非常容易看漏**（本项目坑 14、16 都是这么踩的）。
3. **验证任何机制时，先「消掉兜底」** —— 全局变量掩盖了凭据失效（坑 13）、已有的 `always` 让 `failure` 改错（坑 16）……
   **只要存在两个来源，你就无法判断到底哪个在起作用。**
   ⇒ 这与压测那条纪律是同一条：**"先证明不是测量工具的问题"** —— **先隔离变量，再下结论**。

---

## 附：不想装 Jenkins？GitHub Actions 替代方案

功能等价、云上免费、配置更简单。在仓库根新建 `.github/workflows/api-test.yml`：

```yaml
name: API Test

on:
  push:
    branches: [main]
  schedule:
    - cron: '0 18 * * *'      # UTC 18:00 = 北京时间 02:00

jobs:
  api-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: 安装依赖
        run: pip install -r 01-api-test-framework/requirements.txt
      - name: 执行接口自动化
        working-directory: 01-api-test-framework
        run: python run.py --env=test --ci
      - name: 上传报告
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: api-test-reports
          path: 01-api-test-framework/reports/
```

**选型建议**：
- 生态普及度：**Jenkins > GitHub Actions**（招聘 JD 里写 Jenkins 的远多于 Actions）
- 上手速度：**Actions > Jenkins**
- 推荐路径：**先在本地把 Jenkins 跑通拿经验**（能说清插件、节点、cron 散列），再了解 Actions 作为轻量备选。
