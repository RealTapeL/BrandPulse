# BrandPulse - 品牌情报 Agent 系统

基于商业地产商管运营场景的品牌情报分析系统，聚焦餐饮业态（瑞幸、库迪、星巴克）试点，逐步构建品牌知识库、监控预警和 Agent 智能分析能力。

## 项目结构

```
BrandPulse/
├── README.md                       # 项目说明
├── requirements.txt                # Python 依赖
├── .env                            # 环境变量（本地配置，勿提交）
├── .env.example                    # 环境变量示例
├── docker-compose.yml              # 基础设施部署（可选）
├── brandpulse-infra/               # 基础设施配置
│   ├── docker-compose.yml          # PG + Neo4j + Qdrant
│   ├── .env                        # 基础设施环境变量
│   ├── init-scripts/               # PostgreSQL 初始化脚本
│   └── README.md
│
├── docs/                           # 设计文档和流程图
│   ├── 品牌情报Agent系统建设路线图.drawio
│   ├── 阶段一_品牌知识库建设流程图.drawio
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
│       └── utils/                  # 模块集合
│           ├── config/             # 配置模块
│           │   ├── modules/
│           │   │   └── config.py
│           │   └── stage/
│           ├── db_clients/         # 数据库客户端模块
│           │   ├── modules/
│           │   │   └── db_clients.py
│           │   └── stage/
│           │       └── test_connections.py
│           ├── logger/             # 日志模块
│           │   ├── modules/
│           │   │   └── logger.py
│           │   └── stage/
│           ├── data_collection/    # 数据采集模块
│           │   ├── modules/
│           │   │   └── amap_api.py
│           │   └── stage/
│           │       └── stage1_collect_coffee_stores.py
│           ├── storage/            # 数据存储模块
│           │   ├── modules/
│           │   │   ├── pg_repository.py
│           │   │   ├── neo4j_repository.py
│           │   │   └── qdrant_repository.py
│           │   └── stage/
│           │       ├── stage1_save_stores.py
│           │       └── stage1_build_graph.py
│           ├── analysis/           # 数据分析模块（待扩展）
│           │   ├── modules/
│           │   └── stage/
│           └── agent/              # Agent 模块（待扩展）
│               ├── modules/
│               └── stage/
│
└── tests/                          # 测试代码
```

## 快速开始

### 1. 启动基础设施

```bash
cd brandpulse-infra
docker compose up -d
```

### 2. 安装 Python 依赖

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入高德地图 API Key
```

> **Qdrant 免 Docker 说明**：`.env` 中默认配置了 `QDRANT_PATH=brandpulse-infra/data/qdrant-local`，
> 即本地嵌入模式——qdrant-client 直接读写本地文件，无需启动 Qdrant 服务，API 与服务器模式一致。
> 注意同一时刻只允许一个进程访问该目录。如需改回服务器模式，将 `QDRANT_PATH` 留空即可。
> 该模式下 docker-compose 里的 qdrant 服务可以不启动。


### 4. 测试数据库连接

```bash
cd src
python main.py test
```

### 5. 执行阶段一：采集咖啡品牌门店数据

```bash
python main.py stage1 --cities 北京 上海 广州 --max-pages 2
```

## 当前能力

- ✅ PostgreSQL + Neo4j + Qdrant 基础设施
- ✅ 品牌分类体系设计
- ✅ 咖啡品牌基础数据（瑞幸、库迪、星巴克）
- ✅ 高德地图 API 门店采集模块
- ✅ PG/Neo4j/Qdrant 数据仓储层
- ✅ 阶段一：品牌知识库建设脚本

## 后续计划

- 阶段二：品牌监控与预警（大众点评评分监控、门店变化预警）
- 阶段三：Agent 智能分析（对话式查询、招商建议生成）

## 注意事项

- `.env` 文件包含敏感配置，不要提交到代码仓库
- 生产环境请修改默认密码
- 外部数据采集请遵守相关平台规则
