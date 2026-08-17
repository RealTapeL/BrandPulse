# BrandPulse 品牌情报分析系统

[![CI](https://github.com/RealTapeL/BrandPulse/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/RealTapeL/BrandPulse/actions/workflows/ci.yml)

面向商业地产招商运营场景的可信品牌情报系统。系统按「城市 × 商场/项目 × 品类」登记监测范围，将公开来源记录、来源运行、数据质量、快照、指标与人工映射串成可追溯链路，用于候选品牌筛选和招商线索核验；不把公开评价或内容直接解释为销售、利润或确定招商结论。

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
├── migrations/                     # 应用表迁移（任务、指标、告警、公式、经营数据、数据治理）
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
│   │       ├── indicators/         # 指标层：快照指标、比较池、趋势可比性与公式试验
│   │       ├── api/                # FastAPI：认证、看板、品牌、任务、数据表、公式等
│   │       ├── agent/              # Pydantic AI 工具循环 + Tool registry
│   │       ├── alerts/             # 告警规则与调度器
│   │       └── data_governance/    # 别名、门店匹配、质量扫描、采集血缘
│   ├── frontend/                   # 前端（Vue3 + Element Plus + ECharts + Pinia）
│   └── ml/                         # 情感/NER 与时间序列预测（transformers + scikit-learn）
├── models/                         # 训练后模型保存目录
└── tests/                          # pytest（当前 122 项）
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

# 初始化数据库，读取环境变量或 .env 中的 PostgreSQL 配置
bash scripts/apply_migrations.sh

# 启用数据库用户、三角色权限和安全刷新会话。
# 本机 HTTP 调试才使用 --local-http；正式环境必须通过 HTTPS 运行，不要添加此参数。
.venv/bin/python scripts/configure_production_auth.py --local-http

# 前端（本机 npm 位于 ~/.local/node/bin）
fish_add_path ~/.local/node/bin
cd src/frontend && npm install && npm run build && cd ../..
```

### 启动服务

```bash
redis-server --daemonize yes --port 6379        # Redis 任务队列
bash scripts/start_rq_worker.sh                  # RQ worker：消费采集与 Agent 队列
bash scripts/start_monitoring_scheduler.sh       # 独立每日采集/报告调度器
bash scripts/start_alert_scheduler.sh             # 独立告警检查与通知调度器
bash scripts/start_webbridge.sh                  # 采集通道：WebBridge MCP（ws://127.0.0.1:10086）
bash scripts/start_web.sh                        # Web 平台：FastAPI + 前端静态托管（8000 端口）

# 推荐：一键启动 Redis、RQ Worker、采集/报告调度器、告警调度器、FastAPI、Vite 前端和 WebBridge
bash scripts/start_all.sh
# 查看状态 / 停止本脚本启动的进程
bash scripts/start_all.sh status
bash scripts/start_all.sh stop
# 若默认端口被其他项目占用，脚本会自动顺延；也可显式指定：
# BRANDPULSE_BACKEND_PORT=8001 BRANDPULSE_FRONTEND_PORT=5174 bash scripts/start_all.sh

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
| `POST /api/v1/auth/login` | 用户名密码登录，返回短期 Access Token 并设置 HttpOnly 刷新 Cookie |
| `POST /api/v1/auth/refresh` / `POST .../logout` | 轮换刷新会话 / 注销当前会话 |
| `POST /api/v1/auth/change-password` | 修改自己的密码并注销所有历史会话 |
| `GET|POST|PUT /api/v1/users` | 管理员管理账号、角色、状态和一次性临时密码 |
| `GET  /api/v1/dashboard` | 看板聚合数据（`/api/dashboard` 保留为兼容别名） |
| `GET  /api/v1/brands` | 品牌目录筛选与分页 |
| `GET  /api/v1/brands/filters` | 品类、城市筛选项 |
| `GET  /api/v1/brands/{id}` | 品牌主数据、采集记录与可信数据边界说明 |
| `POST /api/v1/brands/{id}/crawl` | 按已登记 `scope_id` 发起候选采集；不自动确认品牌映射 |
| `POST /api/v1/crawl_jobs` | 创建采集任务并投递 `brandpulse-crawl` RQ 队列（body: brand_id, mall, category, cities?） |
| `GET  /api/v1/crawl_jobs` / `GET .../{id}` | 查询持久化采集任务历史与状态 |
| `GET  /api/v1/indicators` | 指标时序（query: brand_id, indicator, start, end） |
| `GET /api/v1/dashboard/scopes` / `GET /api/v1/dashboard?scope_id=` | 真实项目/品类范围与范围内看板快照 |
| `GET  /api/v1/tables/{name}` | 白名单数据表的服务端筛选、排序、分页；`raw_observations`、`metric_observations` 必须传 `scope_id` |
| `GET|POST|PUT|DELETE /api/v1/formulas` | 自定义指标公式配置 |
| `POST /api/v1/formulas/{id}/run` / `GET .../values?scope_id=` | 按可信范围的 ready/published 快照计算并读取带证据的公式试验结果 |
| `POST /api/v1/operations/preview` / `POST .../import` | 校验并导入“内部经营数据”Excel |
| `GET /api/v1/data-governance/summary` / `POST .../scan` | 数据质量汇总与扫描 |
| `GET /api/v1/data-governance/issues` | 查看、确认和关闭数据质量问题 |
| `GET /api/v1/data-governance/store-aliases` | 查看外部门店别名及人工匹配状态 |
| `GET /api/v1/data-governance/lineage` | 查看真实采集来源、任务和记录数 |
| `GET /api/v1/data-governance/lineage/records` | 按来源批次、采集任务追溯原始记录 |
| `POST /api/v1/agent/execute` | 创建 Agent 任务并投递 `brandpulse-agent` RQ 队列 |
| `GET /api/v1/agent/tasks` / `GET .../tasks/{id}` | 查询持久化任务历史与单任务状态 |
| `POST /api/v1/chat` | 对话式数据问答（需配置 LLM） |
| `POST /api/v1/alerts/check-now` | 立即执行告警检查 |
| `GET /api/v1/alerts/deliveries/list` | 查看逐目标通知、失败原因和重试状态 |
| `GET|POST|PUT|DELETE /api/v1/monitoring/crawl-schedules` | 自动采集计划配置、启停与持久化状态 |
| `GET|POST|PUT|DELETE /api/v1/alerts` / `GET .../alerts/history` | 范围绑定告警、快照证据、通知配置与检查历史 |
| `GET|POST /api/v1/reports` / `GET .../download` | 真实指标快照报告生成、查询和下载 |
| `GET|POST|PUT|DELETE /api/v1/reports/schedules` | 日报/周报定时计划配置 |
| `GET /api/v1/snapshots/{snapshot_id}/history` | 查看快照状态转换历史 |
| `POST /ml/sentiment` | 情感分类推理 |
| `POST /ml/ner` | 命名实体识别推理 |
| `GET /api/v1/ml/datasets` | 公开数据集与已上传数据的登记、校验状态 |
| `POST /api/v1/ml/datasets/upload` | 上传 CSV/XLSX/XLSM 并校验真实销售时序数据 |
| `POST /api/v1/ml/forecasting/train` | 创建训练任务并投递 brandpulse-ml RQ 队列 |
| `GET /api/v1/ml/forecasting/runs` | 查询训练台账、状态和回测指标 |
| `POST /api/v1/ml/forecasting/exports` | 创建 CSV/XLSX 预测导出任务 |
| `GET /api/v1/ml/forecasting/exports/{export_id}/download` | 下载已完成的预测文件 |
| `GET /api/v1/ml/logs` | 查询数据输入、训练和预测导出日志 |
| `GET /api/v1/ml/forecasting/models/{model_id}/forecast` | 读取已生成预测结果 |
| `GET /api/v1/system/health/live` / `GET .../ready` | 无登录依赖的存活与就绪探针 |
| `GET /api/v1/system/configuration` | 受保护的生产配置完备性检查，不返回密钥内容 |
| `GET /metrics` | Prometheus 进程与 HTTP 请求指标 |
| `GET /api/v1/audit/events` | 按操作者、动作、结果和请求 ID 查询操作审计 |

除登录与刷新接口外的业务 API 都需要 `Authorization: Bearer <token>`。变更请求、登录、认证/授权失败和文件下载会写入
`audit_events`，只记录操作者、动作、结果、耗时与请求 ID，不保存正文、密码、刷新令牌或 Access Token。未部署 ML 模型时
推理接口返回 503，不会返回伪造预测。

## 生产登录与权限

生产环境使用 `AUTH_MODE=rbac`，密码以 Argon2id 哈希保存，短期 Access Token 仅存在浏览器内存，刷新令牌只通过
`HttpOnly + Secure + SameSite=Strict` Cookie 保存。初始化命令会生成至少 64 字符的 `AUTH_SECRET`，并在没有管理员时创建
一个必须改密的初始管理员；初始密码只落到本机 `.secrets/brandpulse_initial_admin_password.txt`（权限 0600），不会打印或提交到仓库。

| 角色 | 可做的事 |
|---|---|
| 管理员 | 拥有运营人员所有能力，并管理账号/角色、审计记录和生产配置检查。 |
| 运营人员 | 查看所有业务数据；执行采集、指标/数据治理、经营数据导入、模型训练与导出、监控告警、报告和后台 Agent。 |
| 只读人员 | 查看业务数据、历史记录、已完成报告/预测，并使用仅含查询工具的对话 Agent；不能写入、采集、训练或创建后台任务。 |

正式部署必须设置 `APP_ENV=production`、`AUTH_MODE=rbac`、`AUTH_COOKIE_SECURE=true`，并经 HTTPS 对外提供服务；启动时会拒绝不安全配置。

## 机器学习预测

已完成首个公开基准销售预测模块：数据集登记、真实文件输入、下载校验、时间回测、RQ 后台训练、
训练日志、预测导出、模型元数据、预测结果 API 和前端“机器学习预测”页面。

首个数据集为 GitHub skforecast-datasets 的 store_sales.csv，原始来源为 Kaggle
Store Item Demand Forecasting Challenge。它包含 913,000 条、10 家门店、50 个 SKU
的日销售记录。模型工件只保存在 models/forecasting，数据只保存在 data/raw/ml/benchmark，
不会写入 store_operations。

CLI 操作：

    PYTHONPATH=src/backend:src .venv/bin/python -m ml.forecasting.cli download --dataset store_sales
    PYTHONPATH=src/backend:src .venv/bin/python -m ml.forecasting.cli train --dataset store_sales --validation-days 28 --horizon 14

公开基准模型的 production_eligible 固定为 false；只有获得授权的内部 POS / 客流数据，
完成主数据映射、质量扫描和独立回测后，才能进入生产模型流程。

## 自动监控与报告

看板按 `监测范围（城市 × 项目 × 品类 × 数据集 ID）` 查询；范围来自真实采集任务和数据表，
不再在前端写死“苏州中心·咖啡”。自动采集计划、告警规则和日报/周报计划默认关闭，只有用户
明确启用后才会执行真实浏览器采集或生成报告。

自动采集计划在 Web 页面配置为北京时间固定执行时间（默认每天 09:00），数据库记录计划日期，
同一天不会重复入队。计划默认关闭，启用后由独立的 `brandpulse.monitoring.runner` 进程检查并入队，
不依赖 FastAPI 是否重启；RQ Worker 负责真实执行，来源级结果会分别记录为 `success`、`empty` 或
`failed`。全部来源均无可验证记录时任务失败；部分来源为空时保留已采到的数据，同时在任务和计划中显示警告。

告警检查由独立的 `brandpulse.alerts.runner` 进程负责，FastAPI 不再启动告警调度器。这样运行多个
API 副本时不会重复检查同一条规则或重复发送通知；`bash scripts/start_all.sh` 会默认启动该进程，
也可以通过 `BRANDPULSE_START_ALERT_SCHEDULER=0` 禁用。首次触发、持续异常提醒和恢复事件有独立状态；
持续提醒按规则冷却，邮箱/Webhook 各自持久化投递并采用指数退避，进程中断后会恢复未完成投递。

通知通道必须使用真实凭据验证：邮件读取 `.env` 的 `SMTP_*` 配置，Webhook 由调用者显式提供地址。
例如：

```bash
PYTHONPATH=src/backend:src .venv/bin/python scripts/test_alert_destination.py --email ops@example.com
PYTHONPATH=src/backend:src .venv/bin/python scripts/test_alert_destination.py --webhook https://example.invalid/your-hook
```

发送失败时脚本返回非 0，不会输出 `mock_sent`。

新的公开数据采集会同步写 `raw_record_lineage`：每条点评或小红书记录关联来源 `run_id`，由后台计划
发起时还会关联 `crawl_job_id` 与 `scope_id`。历史记录不会补造无法证明的批次，因此迁移前的数据只保留
已有来源日志，新的记录级血缘从迁移后首次真实采集开始积累。

报告导出为 XLSX（摘要、指标、点评、小红书四个工作表）或 CSV 指标快照。生成前会校验指标、
点评和小红书数据的新鲜度，默认最多 72 小时（`REPORT_MAX_DATA_AGE_HOURS`）；数据过期时会拒绝
生成并记录原因，不会把旧数据包装成当天结论。

## 内部 POS 经营数据

内部经营数据通过“内部经营数据”工作表导入，必须携带业务系统中的 `record_id`、`brand_id`、
`store_id` 和 `record_date`。导入前会校验品牌与门店主数据的真实对应关系，任何未匹配记录都会整批
拒绝；不会根据门店名称猜测归属，也不会生成示例销售额。导入后可通过以下接口检查项目映射并读取
按日销售趋势、订单、客流、客单价和加权坪效：

- `GET /api/v1/operations/readiness?scope_id=<scope_id>`：品牌、门店、项目和经营记录映射准备度
- `GET /api/v1/operations/metrics/sales-trend?scope_id=<scope_id>`：真实 `store_operations` 聚合结果

当前数据库没有内部 POS 记录时，这两个接口会明确返回未就绪或空 `series`；收到授权的 POS 导出文件
后，先在 Web 页面预览校验，再确认导入，最后才进行销售趋势和内部预测训练。

## 运维检查与数据库备份

负载均衡或容器探针使用：

```bash
curl -f http://127.0.0.1:8000/api/v1/system/health/live
curl -f http://127.0.0.1:8000/api/v1/system/health/ready
curl -f http://127.0.0.1:8000/metrics
```

`ready` 会真实检查 PostgreSQL 和 Redis；任一不可用时返回 503。`docker-compose.dev.yml` 的 Prometheus
默认采集宿主机 8000 端口，若显式使用其他后端端口，需要同步修改 `brandpulse-infra/prometheus.yml`。

数据库备份使用 PostgreSQL custom format，不把 `.env` 或密码写进归档：

```bash
bash scripts/backup_postgres.sh
bash scripts/verify_postgres_backup.sh backups/postgres/brandpulse_YYYYmmdd_HHMMSS.dump
```

备份默认写入 `backups/postgres/`（Git 忽略），生成 SHA-256 校验和，并在落盘前通过 `pg_restore --list`
检查归档。默认保留 14 天；可用 `BRANDPULSE_BACKUP_DIR` 和 `BRANDPULSE_BACKUP_RETENTION_DAYS` 调整。
用户级每日 timer 可执行 `bash scripts/install_backup_timer.sh` 安装，默认约 02:30 运行且不需要 root；仍应
定期使用独立临时数据库执行完整恢复演练。

## 可信快照指标

```bash
.venv/bin/python src/backend/main.py indicators [--date 2026-07-29]
```

正式页面读取 `metric_observations`：每一条结果都绑定 `scope_id`、`snapshot_id`、指标版本、比较池、质量状态和来源证据。它们不经过大模型，能够复现和审计。

- **点评公开存量**：累计评价数、观测门店数；明确标为公开存量，不称为近期热度或经营表现。
- **贝叶斯加权口碑**：`WR=(v/(v+m))·R+(m/(v+m))·C`，优先使用同商场同品类比较池；样本不足时如实标记而不强行给分。
- **点评评价份额**：仅在同一范围、同一快照内计算，记录分子、分母及来源。
- **覆盖率与趋势**：来源覆盖率、实体映射覆盖率；评价增量只在相邻快照来源完整、时间有序且累计数可比时输出。

`src/backend/main.py indicators` 仍用于旧兼容日表维护，不能作为正式招商页面、范围告警、报告或公式试验的数据源。自定义公式必须由用户在页面选择范围和 ready/published 快照后显式执行。

## Web 平台

访问 `http://<本机IP>:8000/`，包含：

- **登录页**：真实 `/api/v1/auth/login` 接口；单团队本地部署默认接受非空凭据，也可用环境变量切换为固定账号密码
- **数据看板**：范围内公开观测、快照质量、竞争线索与待处理事项；不显示伪造热度或经营判断
- **品牌列表 / 详情**：搜索、分页、已确认映射的范围内公开观测、最近采集和候选采集
- **Agent 控制台**：输入指令 → PostgreSQL 持久化 → RQ `brandpulse-agent` 队列 → Worker 执行 → 轮询状态 → 展示日志与输出；页面刷新后可恢复历史任务
- **数据表查看**：范围绑定的原始观测、快照指标和门店经营数据的分页、排序、筛选
- **内部经营数据**：在“门店经营数据”表页上传 Excel；系统先校验品牌与门店主数据，通过后才写库
- **指标公式管理**：快照指标口径、自定义安全公式、按所选范围和快照计算并保存证据
- **操作审计**：查看变更、登录和下载记录，并显示当前生产配置缺口

技术栈：FastAPI + Vue3 / Element Plus / ECharts + Pinia + axios（hash 路由）。

## 对话助手

基于 Pydantic AI 的工具循环 agent。模型只做调度与表达，查数、计算全部走工具；工具是现有代码的薄封装：

| 工具 | 说明 |
|------|------|
| `list_monitoring_scopes` | 返回可选的可信监测范围 |
| `get_scope_snapshot_evidence` | 返回范围的快照、来源覆盖和指标证据 |
| `get_brand_evidence` | 只读取已确认映射的品牌公开观测 |
| `list_opportunity_evidence` / `list_data_quality_evidence` | 返回机会线索或数据质量信号的触发证据 |
| `list_business_case_evidence` | 返回开放事项、负责人和处置状态 |
| `query_db` / `list_tables` | 仅管理员高级调试模式可用的只读 SQL 能力 |
| `external_research` | 可选 Agent-Reach：读取/搜索公开网页，不写入 BrandPulse 指标表 |

```bash
.venv/bin/python src/backend/main.py agent                          # 交互式多轮对话
.venv/bin/python src/backend/main.py agent --question "苏州中心咖啡店口碑怎么样"   # 单轮问答
```

需在 `.env` 中配置 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`（OpenAI 兼容接口）。

### Agent-Reach 外部研究（可选）

Agent-Reach 只作为 Agent 的公开互联网研究能力，不替代 BrandPulse 的真实数据采集、数据治理和指标计算链路。默认关闭；启用前请先在独立环境安装并诊断：

```bash
pipx install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto       # 只检查依赖，不修改系统
agent-reach doctor --json
```

确认依赖和权限后，在项目 `.env` 设置 `AGENT_REACH_ENABLED=true`。外部网页读取使用公开 Jina Reader，搜索使用已配置的 Agent-Reach/Exa `mcporter` 后端；请求有超时和长度限制，不接收或保存 Cookie、Token、密码。需要登录态的平台应使用专用账号，并遵守对应平台规则。

## 数据模型

- **维度表**：`malls`（商场，采集时自动登记）、`brands`、`category_dict`
- **可信范围与运行**：`trusted_monitoring_scopes`、`collection_runs`、`source_runs`
- **可信原始与快照**：`raw_observations`、`data_snapshots`、`snapshot_source_results`
- **指标与判断证据**：`metric_observations`、`opportunity_signals`、`trusted_alert_evaluations`、`snapshot_formula_evaluations`
- **兼容历史表**：`dp_shop_metrics`、`xhs_notes`、`brand_heat_daily`、`brand_indicators_daily` 保留历史读，不作为正式判断来源
- **经营表**：`store_operations`（销售、订单、客流、成本、坪效、租售比、合同到期）

## 测试

```bash
# 后端 + ML 测试
PYTHONPATH=.:src/backend:src .venv/bin/python -m pytest tests/ -q

# 前端测试（在 src/frontend 目录）
cd src/frontend
npm run test:unit   # 当前 13 项
npm run cypress     # e2e 1 项
```

## 持续集成

`.github/workflows/ci.yml` 会在代码推送到 `develop`、向 `develop` 提交 Pull Request，或人工触发时执行：

- 在全新的 PostgreSQL 16 数据库中连续应用两次全部初始化 SQL 和迁移，验证顺序和幂等性
- 启动 Redis 7，运行后端测试，并检查 FastAPI 存活与就绪接口
- 运行前端单元测试和 Vite 生产构建
- 使用 Gitleaks 扫描 Git 历史，阻止 API Key、邮箱授权码等密钥进入仓库

本地可使用与 CI 相同的核心命令：

```bash
bash scripts/apply_migrations.sh
PYTHONPATH=.:src/backend:src .venv/bin/python -m pytest tests/ -q
cd src/frontend && npm run test:unit && npm run build
```

## 当前开发分支

- `develop`：集成主线

## 分支约定

- `develop` 为集成主线，新功能从 `develop` 拉 `feature/xxx` 分支，完成后合回
- `main` 用于发布，首次发布时建立

## 后续计划

- 获得授权后接入 POS 与门店主数据，形成真实销售趋势、坪效和内部预测
- 增加角色/项目权限、对象存储以及模型审批发布与回滚
- 将数据库备份接入异机/对象存储，并建立定期完整恢复演练

## 注意事项

- `.env` 包含敏感配置，不要提交到代码仓库
- 生产环境请修改默认数据库密码
- 外部数据采集请遵守平台规则，控制频率
