# Phase 9：公开销售基准验证与内部经营数据准入

## 当前结论

Phase 9 的“内部经营预测生产化”仍未完成，因为项目尚未取得授权的 POS、门店主数据、客流、租金和面积数据。

本阶段新增的是可复现的公开销售基准验证路径：使用公开数据验证下载、来源校验、时序特征、时间回测、预测导出和运行日志。公开数据不写入 `store_operations`，不绑定苏州中心、不创建真实品牌或门店映射，也不能作为内部经营指标或生产预测依据。

## 真实公开数据

数据集：Store Item Demand Forecasting Challenge。

- 原始来源：Kaggle Store Item Demand Forecasting Challenge
- 可复现下载地址：`https://raw.githubusercontent.com/skforecast/skforecast-datasets/main/data/store_sales.csv`
- 来源说明仓库：`https://github.com/skforecast/skforecast-datasets`
- 数据时间：2013-01-01 至 2017-12-31
- 记录数：913,000
- 门店数：10
- 商品数：50
- 必要字段：`date`、`store`、`item`、`sales`
- 本地文件：`data/raw/ml/benchmark/store_sales.csv`
- 本次校验 SHA-256：`038f25690a65149c94f86ddd3deceda20c037a5cfd754cafdfc539a72992f2ed`
- 数据层级：`public_benchmark`
- `production_eligible`：`false`

下载和校验：

```bash
PYTHONPATH=src/backend:src .venv/bin/python -m ml.forecasting.cli \
  download --dataset store_sales
```

命令会检查必要字段、日期、非负销量、空值和 `date/store/item` 重复记录，并生成不纳入 Git 的 manifest。

## 已落地功能

### Web 端数据入口

- `GET /api/v1/ml/datasets`：查看已登记公开数据集和下载状态。
- `POST /api/v1/ml/datasets/{dataset_key}/download`：只允许下载登记过的数据源，不接受任意 URL；下载、校验和失败均写入机器学习运行日志。
- `GET /api/v1/ml/datasets/{dataset_key}/summary`：读取已校验数据的真实记录数、门店数、商品数、日序列和排名摘要。

Web 页面新增“下载并校验”和“公开销售基准摘要”，摘要明确显示数据不会进入内部经营表。

### 预测验证

```bash
PYTHONPATH=src/backend:src .venv/bin/python -m ml.forecasting.cli \
  train --dataset store_sales --validation-days 28 --horizon 14
```

本次真实回测结果：

- 训练集：885,000 条监督样本
- 验证集：14,000 条监督样本
- 验证区间：2017-12-04 至 2017-12-31
- 模型：`HistGradientBoostingRegressor`
- 模型 WAPE：12.28%
- 最优朴素基线：最近 7 期均值
- 基线 WAPE：17.66%
- 模型优于基线：是
- 模型数据层级：`public_benchmark`
- 是否允许内部生产：否

模型工件已生成在本地 `models/forecasting/store_sales/v1/`，该目录被 Git 忽略，不作为代码提交。

## 内部经营数据仍需遵循的准入路径

获得授权 POS 后，仍按以下路径处理：

```text
POS 导出/API
→ 数据契约校验
→ 原始文件与哈希留存
→ 品牌 / 门店 / 项目人工映射
→ 重复、缺失、日期范围、金额和敏感字段检查
→ 预览与业务确认
→ store_operations
→ 销售、订单、客单价、同店增长、坪效等指标
→ 时间切分回测
→ 模型评估、审批、发布和监控
```

公开基准的 `store` 和 `item` 只是数据集维度，不能自动转换为 BrandPulse 的 `brand_id`、`store_id` 或 `scope_id`。系统不会根据名称或数字猜测映射。

## 尚未完成的 Phase 9 内容

- 授权 POS 数据接入和对账。
- 真实品牌、门店、项目映射。
- `store_operations` 的真实记录。
- 同店销售、坪效、租售比和客流转化的内部指标。
- 内部销售预测模型及其生产发布。
- 内部模型实际值回填、漂移监控和回滚演练。

这些内容不能用公开数据替代。当前公开数据路径的完成，代表 Phase 9 的工程验证部分已具备，不代表内部经营预测已经上线。
