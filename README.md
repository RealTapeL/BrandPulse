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
├── brandpulse-infra/               # 基础设施与本地数据
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
│   ├── raw/                        # 原始采集数据 / 调试输出
│   ├── processed/                  # 清洗后数据 / metrics JSON 缓存
│   └── sample/                     # 示例数据
│
├── scripts/                        # 一次性脚本
├── src/                            # 源代码
│   ├── main.py                     # 项目入口
│   └── brandpulse/
│       ├── __init__.py
│       ├── config/                 # 配置模块
│       ├── logger/                 # 日志模块
│       ├── db_clients/             # 数据库客户端（PG / Neo4j / Qdrant）
│       ├── collectors/             # 数据采集
│       │   ├── config/             # crawler_sites.yaml 站点配置
│       │   ├── modules/            # 按功能分包
│       │   │   ├── amap/           # 高德门店采集（api.py / mock.py）
│       │   │   ├── dianping/       # 大众点评（webbridge_extractor.py）
│       │   │   ├── xiaohongshu/    # 小红书（webbridge / search_api 两种方案）
│       │   │   ├── meituan/        # 美团（占位）
│       │   │   ├── generic_web_webbridge_extractor.py  # 配置化爬虫引擎
│       │   │   ├── css_font_decoder.py     # CSS 字体反爬解码
│       │   │   └── cookie_loader.py        # Cookie 导入导出
│       │   └── stage/              # 采集编排（stage1_*）
│       └── storage/                # 数据仓储层（PG / Neo4j / Qdrant / JSON 文件缓存）
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
```

## 小红书采集方案

小红书风控严格，直接爬容易触发账号警告。目前提供两种方案，按推荐程度排序：

### 方案一：Kimi WebBridge（推荐）

驱动树莓派桌面 Chromium 中**已登录的真实浏览器**采集，不新建浏览器实例。

```bash
# 1. 树莓派桌面 Chromium 安装 Kimi WebBridge 扩展，并登录小红书小号
# 2. WebBridge MCP 服务已由 systemd 托管（开机自启）
sudo systemctl status webbridge-mcp
# 如需手动启动：npx -y kimi-webbridge mcp

# 3. 运行采集（不指定 --site 会自动执行大众点评 + 小红书）
cd /home/lsy/BrandPulse/src
source ../.venv/bin/activate
python main.py crawl --brand-id LK001 --brand-name 瑞幸咖啡 --cities 北京

# 仅小红书
python main.py crawl --site xiaohongshu_webbridge --brand-id LK001 --brand-name 瑞幸咖啡 --cities 北京
```

### 方案二：第三方搜索 API（BettaFish 思路）

不访问小红书页面，调用 Bocha / Tavily 搜索 API 拿公开结果（只有标题/链接/摘要，无互动数）。

```bash
# .env 中配置 BOCHA_API_KEY 或 TAVILY_API_KEY
# crawler_sites.yaml 中将 xiaohongshu_search_api 的 enabled 改为 true
python main.py crawl --site xiaohongshu_search_api --brand-id LK001 --brand-name 瑞幸咖啡 --cities 北京
```

> 所有方案采集结果都会**同时写入 PostgreSQL 和本地 JSON 缓存**（`data/processed/metrics_*.json`）。设置 `DISABLE_METRICS_DB=true` 可只用文件缓存。

## 大众点评采集方案（WebBridge）

驱动已登录大众点评的真实浏览器采集，支持**整页门店列表**和**商场级搜索**。

```bash
# 品牌 × 城市：不指定 --site 会自动执行大众点评 + 小红书
python main.py crawl --brand-id LK001 --brand-name 瑞幸咖啡 --cities 苏州

# 仅大众点评（--place 限定商场）
python main.py crawl --site dianping_webbridge --brand-id LK001 --brand-name 咖啡 --cities 苏州 --place 苏州中心
```

注意：点评风控较严，新开搜索页可能触发验证码。触发后 extractor 会等待 120 秒，去桌面浏览器手动点掉验证码即自动继续。

## 数据模型（热度 / 布局 / 分布）

对应 `docs/品牌热度布局分布_数据表设计.drawio`：

- **维度表**：`malls`（商场，自动从点评采集登记）、`brands`
- **原始表**：`stores`（高德）、`xhs_notes`（小红书笔记）、`dp_shop_metrics`（点评门店指标）
- **聚合表**：`brand_heat_daily`（品牌×城市×商场×日期×平台 热度，AI 查询主入口）
- **视图**：`brand_distribution`（品牌×城市×商场门店数）

迁移脚本：`brandpulse-infra/init-scripts/02_create_mall_heat_tables.sql`

## Superset 数据看板

```text
地址: http://192.168.0.111:8088
账号: admin / admin123（生产环境请修改）
```

- 精简部署：pip 安装 + PostgreSQL 元数据库（无 Docker/Redis/Celery），systemd 托管（`superset.service`）
- 看板「招商品牌情报看板」：品牌热度趋势、商场×品牌表现、门店分布地图、分布明细
- 重建看板：`python scripts/build_superset_dashboard.py`（在 superset venv 中运行）

## 当前能力

- ✅ PostgreSQL + Qdrant 本地基础设施
- ✅ 完整品牌分类体系（6 大业态 / 24 品类 / 56 细分）
- ✅ 咖啡品牌基础数据（瑞幸、库迪、星巴克）
- ✅ 高德地图 API 门店采集（品牌清单从 PG 读取）
- ✅ 小红书采集（Kimi WebBridge 真实浏览器 / 搜索 API 两种方案）
- ✅ 大众点评采集（WebBridge 整页门店 + 商场级 --place 搜索，城市 ID 已实测校准）
- ✅ 热度/布局/分布数据模型（malls / xhs_notes / dp_shop_metrics / brand_heat_daily / brand_distribution）
- ✅ Superset 招商品牌情报看板（热度趋势 / 商场矩阵 / 分布地图）
- ✅ PG 数据仓储层 + Neo4j 降级（竞品关系由 PG 表维护）
- ✅ 配置化通用爬虫引擎（crawler_sites.yaml + extractor 插件）
- ✅ metrics 双写：PostgreSQL + 本地 JSON 文件缓存
- ✅ systemd 托管：superset / webbridge-mcp / postgresql / apache2(Adminer)
- ✅ 测试：`pytest tests/` 通过（19 项）

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
