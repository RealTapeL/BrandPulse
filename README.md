# BrandPulse - 品牌情报 Agent 系统

基于商业地产商管运营场景的品牌情报分析系统，聚焦餐饮业态（瑞幸、库迪、星巴克）试点，逐步构建品牌知识库、监控预警和 5-Agent 智能分析能力。

## 项目结构

```
BrandPulse/
├── README.md                       # 项目说明
├── requirements.txt                # Python 依赖
├── pytest.ini                     # pytest 配置
├── .env                            # 环境变量（本地配置，勿提交）
├── .env.example                    # 环境变量示例
├── brandpulse-infra/               # 基础设施配置
│   ├── docker-compose.yml          # PG + Neo4j + Qdrant（可选）
│   ├── .env                        # 基础设施环境变量
│   ├── init-scripts/               # PostgreSQL 初始化脚本
│   ├── data/                       # 本地数据（Qdrant 嵌入、cookie 等，不提交）
│   └── README.md
│
├── docs/                           # 设计文档和流程图
│   ├── PRD.md                      # 产品需求文档
│   ├── BrandPulse_5-Agent系统架构.drawio
│   ├── 品牌分类体系.drawio
│   └── 餐饮业态数据采集范围.drawio
│
├── data/                           # 数据目录
│   ├── raw/                        # 原始采集数据
│   ├── processed/                  # 清洗后数据
│   └── sample/                     # 示例数据
│
├── notebooks/                      # 分析 Notebook
├── scripts/                        # 一次性脚本
├── src/                            # 源代码
│   ├── main.py                     # 项目入口
│   └── brandpulse/
│       ├── __init__.py
│       ├── config/                 # 配置模块
│       ├── logger/                 # 日志模块
│       ├── db_clients/             # 数据库客户端（PG / Neo4j / Qdrant）
│       ├── collectors/             # 数据采集（高德 / 大众点评 / Excel）
│       ├── storage/                # 数据仓储层（PG / Neo4j / Qdrant）
│       ├── analysis/               # 数据分析模块（待扩展）
│       ├── agent/                  # 5-Agent 流水线（待扩展）
│       ├── knowledge/              # Chunk / Embedding / RAG（待扩展）
│       └── panel/                  # Streamlit 面板（待扩展）
│
└── tests/                          # 测试代码
```

## 快速开始

### 1. 环境要求

- Python 3.13
- PostgreSQL（本机已通过 apt 安装）
- 可选：Neo4j、Qdrant（本机因 4GB 内存，Neo4j 已跳过，竞品关系由 PG 兜底）

### 2. 安装 Python 依赖

```bash
cd /home/lsy/BrandPulse
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 大众点评爬虫需要 Playwright 浏览器
python -m playwright install chromium
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 AMAP_KEY、LLM/Embedding 配置等
```

> **Qdrant 免 Docker 说明**：`.env` 中默认配置了 `QDRANT_PATH=brandpulse-infra/data/qdrant-local`，
> 即本地嵌入模式——qdrant-client 直接读写本地文件，无需启动 Qdrant 服务，API 与服务器模式一致。
> 注意同一时刻只允许一个进程访问该目录。如需改回服务器模式，将 `QDRANT_PATH` 留空即可。

### 4. 测试数据库连接

```bash
cd /home/lsy/BrandPulse/src
source ../.venv/bin/activate
python main.py test
```

### 5. 阶段一：品牌知识库建设

```bash
# 高德门店采集（mock 模式，无需 AMAP_KEY）
python main.py stage1 --cities 北京 上海 广州 --use-mock

# 大众点评指标采集（mock 模式）
python main.py dianping --cities 北京 上海 广州 --brand-ids LK001 KD001 SB001 --use-mock
```

## 大众点评 Cookie 登录方案

大众点评页面为 JS 渲染，需使用 Playwright + 本地浏览器 cookies 才能真实抓取。

### 1. 在本地电脑浏览器登录大众点评

### 2. 导出 cookies

安装浏览器扩展（推荐 Chrome/Edge）：
- [Cookie-Editor](https://chrome.google.com/webstore/detail/cookie-editor/hlkenndedjnhfmakkmjigbnlnbhlejhe)
- [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaklbhjkcbcfmnmvgfe)

导出时选择 **JSON** 格式，保存为 `dianping_cookies.json`。

### 3. 传到树莓派

```bash
# 在本地电脑执行（替换为树莓派实际 IP）
scp dianping_cookies.json lsy@192.168.0.111:/home/lsy/BrandPulse/brandpulse-infra/data/cookies/
```

### 4. 验证 cookies 已加载

```bash
cd /home/lsy/BrandPulse
source .venv/bin/activate
python scripts/verify_cookies.py dianping
```

### 5. 运行真实大众点评采集

```bash
cd /home/lsy/BrandPulse/src
source ../.venv/bin/activate
python main.py dianping --cities 北京 --brand-ids LK001
```

> 首次调试可临时关闭无头模式：修改 `collectors/modules/dianping_crawler.py` 中 `headless=True` 为 `headless=False`，
> 观察浏览器行为。采集成功后建议改回头less模式。

## 大众点评远程 Edge/Chrome 方案（CDP）

如果你希望大众点评**浏览器运行在你本地电脑**，爬虫在树莓派上通过 CDP 远程控制本地浏览器，步骤如下：

### 1. 在本地电脑启动 Edge 并开放调试端口

**Windows**（PowerShell / CMD）：
```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222
```

**macOS**：
```bash
/Applications/Microsoft\ Edge.app/Contents/MacOS/Microsoft\ Edge --remote-debugging-port=9222
```

**Linux**：
```bash
microsoft-edge --remote-debugging-port=9222
```

> 启动后，先手动登录大众点评，保持浏览器窗口开启。

### 2. 查看本地电脑 IP

Windows：
```powershell
ipconfig
```

macOS / Linux：
```bash
ifconfig
```

假设本地电脑 IP 为 `192.168.0.100`。

### 3. 在树莓派 .env 中配置 CDP 地址

```bash
cd /home/lsy/BrandPulse
source .venv/bin/activate
# 编辑 .env，添加或修改：
DIANPING_CDP_URL=http://192.168.0.100:9222
```

### 4. 运行爬虫

```bash
cd /home/lsy/BrandPulse/src
source ../.venv/bin/activate
python main.py dianping --cities 北京 --brand-ids LK001
```

爬虫会连接你本地电脑的 Edge，使用你已登录的 session 进行页面渲染和爬取。

> 注意：
> - 本地电脑防火墙需允许 9222 端口访问。
> - 爬取过程中不要关闭本地 Edge 窗口。
> - 树莓派和本地电脑必须在同一局域网。

## 大众点评树莓派 X11 登录方案

如果你不想在本地电脑维持一个 Edge 窗口，也可以在树莓派上启动可视化浏览器，通过 X11 转发把窗口显示到你的 MacBook 上，登录后保存 cookies。

### 1. MacBook 安装 XQuartz

```bash
brew install --cask xquartz
```

安装后启动 XQuartz 应用。

### 2. 通过 X11 转发 SSH 到树莓派

```bash
ssh -X lsy@192.168.0.111
```

### 3. 运行登录模式

```bash
cd /home/lsy/BrandPulse/src
source ../.venv/bin/activate
python main.py dianping --login-mode
```

会弹出一个 Chromium 浏览器窗口（显示在你的 MacBook 上）。

### 4. 手动登录大众点评

1. 在弹出的浏览器窗口中访问 https://www.dianping.com
2. 扫码或密码登录
3. 回到终端，按回车键保存 cookies

Cookies 会保存到：
`/home/lsy/BrandPulse/brandpulse-infra/data/cookies/dianping_cookies.json`

### 5. 运行正常采集

```bash
python main.py dianping --cities 北京 --brand-ids LK001
```

> 注意：X11 转发对网络延迟敏感，首次打开浏览器可能较慢。如果窗口显示异常，建议改用 CDP 方案。

## 当前能力

- ✅ PostgreSQL + Qdrant 本地基础设施
- ✅ 完整品牌分类体系（6 大业态 / 24 品类 / 56 细分）
- ✅ 咖啡品牌基础数据（瑞幸、库迪、星巴克）
- ✅ 高德地图 API 门店采集（品牌清单从 PG 读取）
- ✅ 大众点评指标采集模块（Playwright + Cookie / mock 降级）
- ✅ PG 数据仓储层（brands / stores / brand_metrics / brand_relationships）
- ✅ Neo4j 降级：竞品关系由 PG 表维护
- ✅ 测试：`pytest tests/` 通过

## 后续计划

- M2 数据清洗与标准化（品牌别名、门店去重、质量校验、data_source_logs）
- M3 查询面板（Streamlit）
- M4 布局分析与数据 API
- M5 Chunk 知识库 + Embedding
- M6 监控与预警（阶段二）
- M7 5-Agent 流水线（阶段三）

## 注意事项

- `.env` 文件包含敏感配置，不要提交到代码仓库
- 生产环境请修改默认数据库密码
- 外部数据采集请遵守相关平台规则，控制频率
