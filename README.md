# BrandPulse 品牌情报分析系统

面向商业地产招商运营场景的品牌情报系统。按「商场 + 品类」采集大众点评、小红书的公开数据，用确定性指标模型计算口碑、热度、声量份额，通过 Web 平台展示，并提供对话式数据问答。

## 项目结构

```
BrandPulse/
├── README.md
├── requirements.txt                # Python 依赖
├── pytest.ini                      # pytest 配置
├── .env / .env.example             # 环境变量（.env 不提交）
├── env.dev.example                 # 本地开发环境变量模板
├── docker-compose.dev.yml          # 开发依赖编排（Postgres / Redis / Prometheus，可选）
├── brandpulse-infra/
│   ├── init-scripts/               # PostgreSQL 建表脚本（01–05）
│   ├── prometheus.yml              # Prometheus scrape 样例
│   ├── coffee_brand_database_schema.sql  # 咖啡品牌库表结构参考
│   └── data/                       # 本地数据（不提交）
├── docs/                           # PRD 与 drawio 架构图
├── migrations/                     # 新增表迁移（crawl_jobs / indicators / alerts）
├── data/                           # raw / processed / normalized / invalid / labelled
├── scripts/                        # 服务启动脚本
├── src/
│   ├── backend/                    # 后端（Python）
│   │   ├── main.py                 # CLI 入口
│   │   └── brandpulse/
│   │       ├── config/             # 读取 .env
│   │       ├── logger/             # 日志
│   │       ├── db_clients/         # PostgreSQL 客户端（单例）
│   │       ├── collectors/         # 采集层：crawler + extractor + WebBridge + RQ queue
│   │       │   ├── config/         #   crawler_sites.yaml 站点配置
│   │       │   ├── extractors/     #   大众点评 / 小红书 extractor 插件
│   │       │   ├── amap/           #   高德门店采集
│   │       │   ├── schemas.py      #   pydantic 采集 schema
│   │       │   └── pipelines.py    #   解析/标准化/校验 pipeline
│   │       ├── storage/            # 仓储层：PG 表 + JSON 文件缓存双写
│   │       ├── indicators/         # 指标层：口碑 / 热度 / SOV / 趋势 + aggregate job
│   │       ├── api/                # FastAPI：看板 + crawl_jobs + indicators + alerts
│   │       ├── agent/              # Pydantic AI 工具循环 + Tool registry
│   │       └── alerts/             # 告警规则与调度器
│   ├── frontend/                   # 前端（Vue3 + Element Plus + ECharts + Pinia）
│   └── ml/                         # 情感分类 & NER 训练/推理（transformers）
├── models/                         # 训练后模型保存目录
└── tests/                          # pytest（52+ 项）
```

## 快速开始

### 环境要求

- Python 3.12+，Node.js 20+，PostgreSQL（本机库 `brandpulse`），Redis（任务队列）
- 数据采集依赖 Kimi WebBridge 浏览器扩展（Edge / Chrome），需在本机桌面浏览器登录大众点评、小红书账号

### 安装

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt

cp env.dev.example .env   # 编辑填入 LLM_*（对话助手）、REDIS_URL 等

# 初始化数据库，按顺序执行脚本
for f in brandpulse-infra/init-scripts/*.sql migrations/*.sql; do
  echo 'yang2004.' | sudo -S -u postgres psql -d brandpulse -f "$f"
done

# 前端（本机 npm 位于 ~/.local/node/bin）
fish_add_path ~/.local/node/bin
cd src/frontend && npm install && npm run build && cd ../..
```

### 启动服务

```bash
redis-server --daemonize yes --port 6379        # Redis 任务队列
bash scripts/start_rq_worker.sh                  # RQ worker：消费 brandpulse-crawl 队列
bash scripts/start_webbridge.sh                  # 采集通道：WebBridge MCP（ws://127.0.0.1:10086）
bash scripts/start_web.sh                        # Web 平台：FastAPI + 前端静态托管（8000 端口）

# 开发模式（热重载，前端独立 5173）
cd src/frontend && npm run dev
```

## 数据采集

商场 × 品类模式（主要用法）：

```bash
.venv/bin/python src/backend/main.py crawl --mall 苏州中心 --category 咖啡 --cities 苏州
```

- 不指定 `--site` 时依次采集大众点评和小红书；`--site dianping_webbridge` / `--site xiaohongshu_webbridge` 可单独指定
- 采集驱动的是桌面浏览器中已登录的真实会话；触发验证码时在浏览器里手动通过即可自动继续
- 结果双写 PostgreSQL 与 `data/processed/` 下的 JSON 缓存

## 后端 API 接口

| 接口 | 说明 |
|------|------|
| `GET  /api/dashboard` | 看板聚合数据 |
| `POST /api/v1/crawl_jobs` | 创建采集任务并 enqueue（body: brand_id, mall, category, cities?） |
| `GET  /api/v1/crawl_jobs/{id}` | 查询任务状态 |
| `GET  /api/v1/indicators` | 指标时序（query: brand_id, indicator, start, end） |
| `POST /api/v1/alerts/check-now` | 立即执行告警检查 |
| `POST /ml/sentiment` | 情感分类推理 |
| `POST /ml/ner` | 命名实体识别推理 |

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

访问 `http://<本机IP>:8000/`，包含：

- **登录页**：localStorage token，受路由守卫保护
- **数据看板**：KPI 卡片、指标趋势图、双平台明细表
- **品牌列表 / 详情**：搜索、分页、热度趋势、最近采集、发起采集
- **Agent 控制台**：输入指令 → POST `/api/v1/agent/execute` → 轮询任务 → 展示日志与输出
- **数据表查看**：点评门店 / 小红书笔记 / 指标日表的分页、排序、筛选
- **指标公式管理**：内置指标口径展示与自定义公式

技术栈：FastAPI + Vue3 / Element Plus / ECharts + Pinia + axios（hash 路由）。

## 对话助手

基于 Pydantic AI 的工具循环 agent。模型只做调度与表达，查数、计算全部走工具；工具是现有代码的薄封装：

| 工具 | 说明 |
|------|------|
| `list_tables` | 返回业务表结构，供模型写 SQL 前参考 |
| `query_db` / `run_sql` | 只读 SQL（仅 SELECT/WITH，拦截多语句与写操作，限 100 行） |
| `query_brand` | 按 brand_id 查询品牌基础信息 |
| `start_crawl` | 把采集任务入队 RQ，返回 job_id |
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
# 后端 + ML 测试
PYTHONPATH=src/backend:src .venv/bin/python -m pytest tests/ -q   # 52 项

# 前端测试（在 src/frontend 目录）
cd src/frontend
npm run test:unit   # 9 项
npm run cypress     # e2e 1 项
```

## 当前开发分支

- `develop`：集成主线（前端原型 1–3 阶段已合并）
- `feat/collectors-20260730`：本次 backend 工程能力分支（A/B/C/D/F/G/E/H）

## 分支约定

- `develop` 为集成主线，新功能从 `develop` 拉 `feature/xxx` 分支，完成后合回
- `main` 用于发布，首次发布时建立

## 后续计划

- Agent Console 后端接口 `/api/v1/agent/execute` 接入前端（前端已按契约实现轮询展示）
- `/api/formulas` 自定义公式服务端表达式沙箱
- 前端与真实后端对接（关闭 VITE_USE_MOCK）
- 品牌别名归一、门店去重、采集血缘
- ML 模型训练调优与模型管理

## 注意事项

- `.env` 包含敏感配置，不要提交到代码仓库
- 生产环境请修改默认数据库密码
- 外部数据采集请遵守平台规则，控制频率
