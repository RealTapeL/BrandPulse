# BrandPulse 基础设施

项目只依赖一个数据库：PostgreSQL。本机直装，不使用 Docker。

## 目录结构

```
brandpulse-infra/
├── init-scripts/                   # PostgreSQL 建表脚本，按序号顺序执行
│   ├── 01_create_tables.sql        # 实体表（brands / stores / category_dict 等）+ 咖啡品牌预置数据
│   ├── 02_create_mall_heat_tables.sql  # 热度模型（malls / xhs_notes / dp_shop_metrics / brand_heat_daily）
│   └── 03_create_indicator_tables.sql  # 指标表（brand_indicators_daily）
├── coffee_brand_database_schema.sql    # 咖啡品牌库表结构参考（设计稿）
├── data/                           # 本地数据（不提交）
└── README.md
```

## 初始化

```bash
psql -U postgres -d brandpulse -f init-scripts/01_create_tables.sql
psql -U postgres -d brandpulse -f init-scripts/02_create_mall_heat_tables.sql
psql -U postgres -d brandpulse -f init-scripts/03_create_indicator_tables.sql
```

`01` 脚本会预置瑞幸、库迪、星巴克三个品牌的基础数据及竞品关系；`02`、`03` 为采集与指标功能依赖的表结构，缺了会导致采集入库或指标计算报错。

## 连接配置

Python 侧通过项目根目录 `.env` 配置数据库连接（参考 `.env.example`），客户端代码在 `src/backend/brandpulse/db_clients/`。

## 说明

- 早期方案中的 Neo4j / Qdrant 已移除，竞品关系由 PG 的 `brand_relationships` 表维护，文本知识库方案待阶段三重新设计
- 生产部署前请修改默认数据库密码，且不要将 `.env` 提交到代码仓库
