# BrandPulse 基础设施部署

本项目一键部署 BrandPulse 所需的三个核心数据库：

- **PostgreSQL**：存储品牌、门店、经营数据等结构化数据
- **Neo4j**：存储品牌关系网络（竞品、同集团、同商场等）
- **Qdrant**：存储文本知识库的向量，供大模型 RAG 检索

## 目录结构

```
brandpulse-infra/
├── docker-compose.yml      # Docker Compose 配置文件
├── .env                    # 环境变量（已配置默认密码，生产环境请修改）
├── .env.example            # 环境变量示例
├── init-scripts/           # PostgreSQL 初始化脚本
│   └── 01_create_tables.sql
├── data/                   # 数据持久化目录
│   ├── postgres/
│   ├── neo4j/
│   └── qdrant/
└── README.md
```

## 前置要求

- 已安装 Docker
- 已安装 Docker Compose
- 端口 5432、7474、7687、6333、6334 未被占用

## 快速启动

```bash
cd brandpulse-infra

# 1. 启动服务（首次启动会下载镜像并初始化数据库）
docker-compose up -d

# 2. 查看服务状态
docker-compose ps

# 3. 查看日志
docker-compose logs -f
```

## 访问方式

| 服务 | 访问地址 | 默认账号 | 默认密码 |
|------|----------|----------|----------|
| PostgreSQL | `localhost:5432` | `brandpulse` | `brandpulse123` |
| Neo4j Browser | `http://localhost:7474` | `neo4j` | `brandpulse123` |
| Neo4j Bolt | `bolt://localhost:7687` | `neo4j` | `brandpulse123` |
| Qdrant HTTP | `http://localhost:6333` | - | - |
| Qdrant Dashboard | `http://localhost:6333/dashboard` | - | - |

## 停止服务

```bash
docker-compose down
```

## 完全重置（会清空所有数据）

```bash
docker-compose down -v
rm -rf data/postgres/* data/neo4j/* data/qdrant/*
```

## 验证连接

### PostgreSQL

```bash
docker exec -it brandpulse-postgres psql -U brandpulse -d brandpulse -c "SELECT * FROM brands;"
```

### Neo4j

打开浏览器访问 `http://localhost:7474`，输入账号密码后执行：

```cypher
MATCH (n) RETURN n LIMIT 25
```

（首次启动无数据，后续可通过数据导入脚本写入）

### Qdrant

```bash
curl http://localhost:6333/collections
```

## 数据初始化说明

PostgreSQL 启动时会自动执行 `init-scripts/01_create_tables.sql`，创建：

- 分类字典表
- 品牌基础表
- 公司表
- 门店表
- 品牌指标时序表
- 门店经营数据表
- 品牌联系人表
- 品牌关系表
- 数据采集日志表

并预置瑞幸、库迪、星巴克三个品牌的基础数据及竞品关系。

## 安全提示

- 默认密码仅用于本地开发测试
- 生产部署前务必修改 `.env` 中的密码
- 不要将 `.env` 文件提交到代码仓库

## 下一步

服务启动后，可以：

1. 使用 Python + SQLAlchemy 连接 PostgreSQL 读写品牌数据
2. 使用 Neo4j Python Driver 构建品牌关系图谱
3. 使用 Qdrant Client 写入文本向量，搭建 RAG 知识库
4. 调用高德地图等开放 API 采集咖啡品牌门店数据
