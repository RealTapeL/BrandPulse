# BrandPulse 品牌情报分析系统

面向商业地产招商运营场景的品牌情报系统。按「商场 + 品类」采集大众点评、小红书的公开数据，用确定性指标模型计算口碑、热度、声量份额，通过 Web 平台展示，并提供对话式数据问答。

## 项目结构

```
BrandPulse/
├── README.md
├── requirements.txt                # Python 依赖
├── pytest.ini                      # pytest 配置
├── .env / .env.example             # 环境变量（.env 不提交）
├── brandpulse-infra/
│   ├── init-scripts/               # PostgreSQL 建表脚本（01 实体表 / 02 热度表 / 03 指标表）
│   ├── coffee_brand_database_schema.sql  # 咖啡品牌库表结构参考
│   └── data/                       # 本地数据（不提交）
├── docs/                           # PRD 与 drawio 架构图
├── data/                           # raw（原始留存）/ processed（JSON 缓存）/ sample（模板）
├── scripts/                        # 服务启动脚本（start_web.sh / start_webbridge.sh 等）
├── src/
│   ├── backend/                    # 后端（Python）
│   │   ├── main.py                 # CLI 入口（test / stage1 / crawl / indicators / agent）
│   │   └── brandpulse/
│   │       ├── config/             # 读取 .env
│   │       ├── logger/             # 日志
│   │       ├── db_clients/         # PostgreSQL 客户端（单例）
│   │       ├── collectors/         # 采集层：crawler 引擎 + 平台 extractor + WebBridge 客户端
│   │       │   ├── config/         #   crawler_sites.yaml 站点配置
│   │       │   ├── extractors/     #   大众点评 / 小红书 extractor 插件
│   │       │   ├── amap/           #   高德门店采集
│   │       │   └── stage/          #   采集编排（stage1_*）
│   │       ├── storage/            # 仓储层：PG 表 + JSON 文件缓存双写
│   │       ├── indicators/         # 指标层：口碑 / 热度 / SOV / 趋势（纯函数 + 编排分离）
│   │       ├── api/                # FastAPI：看板数据接口 + 前端静态托管
│   │       └── agent/              # 对话助手（Pydantic AI 工具循环）
│   └── frontend/                   # 前端（Vue3 + Element Plus + ECharts）
└── tests/                          # pytest（47 项）
```

## 快速开始

### 环境要求

- Python 3.12+，Node.js 20+，PostgreSQL（本机库 `brandpulse`）
- 数据采集依赖 Kimi WebBridge 浏览器扩展（Edge / Chrome），需在本机桌面浏览器登录大众点评、小红书账号

### 安装

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env   # 编辑填入 LLM_*（对话助手）、高德 key 等

# 初始化数据库，按顺序执行三个脚本
psql -U postgres -d brandpulse -f brandpulse-infra/init-scripts/01_create_tables.sql
psql -U postgres -d brandpulse -f brandpulse-infra/init-scripts/02_create_mall_heat_tables.sql
psql -U postgres -d brandpulse -f brandpulse-infra/init-scripts/03_create_indicator_tables.sql

# 前端构建（产物 dist/ 由后端静态托管）
cd src/frontend && npm install && npm run build && cd ../..
```

### 启动服务

```bash
bash scripts/start_webbridge.sh   # 采集通道：WebBridge MCP（ws://127.0.0.1:10086）
bash scripts/start_web.sh         # Web 平台：FastAPI + 前端静态托管（8000 端口）
```

## 数据采集

商场 × 品类模式（主要用法）：

```bash
.venv/bin/python src/backend/main.py crawl --mall 苏州中心 --category 咖啡 --cities 苏州
```

- 不指定 `--site` 时依次采集大众点评和小红书；`--site dianping_webbridge` / `--site xiaohongshu_webbridge` 可单独指定
- 采集驱动的是桌面浏览器中已登录的真实会话；触发验证码时在浏览器里手动通过即可自动继续
- 结果双写 PostgreSQL 与 `data/processed/` 下的 JSON 缓存

品牌 × 城市模式（保留）：

```bash
.venv/bin/python src/backend/main.py crawl --brand-id LK001 --brand-name 瑞幸咖啡 --cities 苏州
```

## 指标计算

```bash
.venv/bin/python src/backend/main.py indicators [--date 2026-07-29]
```

指标全部由确定性代码计算，不经过大模型，可复现可审计。口径（`src/backend/brandpulse/indicators/`，公式参数为文件头常量，可用历史数据校准）：

- **口碑分**：贝叶斯加权 `WR=(v/(v+m))·R+(m/(v+m))·C`。v=评价数，R=门店评分，C=全城加权均分，m=评价数中位数。评价少的店分数被拉向全城均值，避免小样本门店分数虚高
- **热度指数**：固定基准对数归一 `100·ln(1+v)/ln(1+50000)`。对数压缩长尾，固定基准保证跨天、跨商场可比
- **SOV 声量份额**：门店评价数 ÷ 同商场同品类总评价数，衡量商场内的相对竞争力
- **趋势**：周环比动量 + 近 4 期波动率（变异系数）。数据不足 2 期时不产出，属正常状态

结果写入 `brand_indicators_daily`。

## Web 平台

访问 `http://<本机IP>:8000/`，包含四个页面：

- **数据看板**：KPI 卡片、四象限气泡图（口碑×热度×SOV）、各指标对比图、双平台明细表
- **对话助手**：对话式数据问答（前端已完成，后端接口 `/api/chat` 待接入）
- **数据表查看**：点评门店 / 小红书笔记 / 指标日表的分页、排序、筛选
- **指标公式管理**：内置指标口径展示；自定义公式的增删改与启停（服务端 `/api/formulas` 待接入）

技术栈：FastAPI（`src/backend/brandpulse/api/`，接口 `GET /api/dashboard`）+ Vue3 / Element Plus / ECharts（hash 路由，前端内已预留后端接口契约与降级逻辑）。

## 对话助手

基于 Pydantic AI 的工具循环 agent。模型只做调度与表达，查数、计算全部走工具；工具是现有代码的薄封装：

| 工具 | 说明 |
|------|------|
| `list_tables` | 返回业务表结构，供模型写 SQL 前参考 |
| `query_db` | 只读 SQL（仅 SELECT/WITH，拦截多语句与写操作，限 100 行） |
| `run_indicators` | 调用指标管道，刷新当日指标 |
| `crawl` | 驱动浏览器采集指定商场 × 品类数据（约 40 秒） |

```bash
.venv/bin/python src/backend/main.py agent                          # 交互式多轮对话
.venv/bin/python src/backend/main.py agent --question "苏州中心咖啡店口碑怎么样"   # 单轮问答
```

需在 `.env` 中配置 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`（OpenAI 兼容接口）。

## 数据模型

- **维度表**：`malls`（商场，采集时自动登记）、`brands`、`category_dict`
- **原始表**：`stores`（高德）、`dp_shop_metrics`（点评门店指标）、`xhs_notes`（小红书笔记）
- **聚合表**：`brand_heat_daily`（品牌 × 城市 × 商场 × 日期 × 平台热度）
- **指标表**：`brand_indicators_daily`（口碑 / 热度 / SOV / 趋势，按日按门店）

## 测试

```bash
.venv/bin/python -m pytest tests/ -q   # 47 项
```

## 分支约定

- `develop` 为集成主线，新功能从 `develop` 拉 `feature/xxx` 分支，完成后合回
- `main` 用于发布，首次发布时建立

## 后续计划

- 对话助手与自定义公式的后端接口（`/api/chat`、`/api/formulas`）接入 Web 平台
- 数据清洗与标准化（品牌别名归一、门店去重、采集血缘）
- 品牌监控与预警（规则引擎 + 定时采集 + 企业微信/钉钉推送）
- 机器学习预测（独立分支）

## 注意事项

- `.env` 包含敏感配置，不要提交到代码仓库
- 生产环境请修改默认数据库密码
- 外部数据采集请遵守平台规则，控制频率
