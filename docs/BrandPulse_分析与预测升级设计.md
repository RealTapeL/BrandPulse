# BrandPulse 分析与可信预测升级设计

版本：Phase 0 / 2026-08-17
适用范围：BrandPulse 当前 `develop` 分支
试点范围：苏州 × 苏州中心 × 咖啡

## 1. 升级目标与事实边界

BrandPulse 当前已经具备真实采集、来源运行、数据治理、可信快照、确定性指标、告警、报告、Agent 和机器学习任务台账。本次升级不增加新的采集平台，而是把已有真实数据沉淀为可复现、可追溯的分析底座，并逐步形成外部公开数据预测能力。

本项目不把大众点评、小红书或高德数据解释为销售、利润、客流、坪效或确定招商结果。没有授权的 POS、客流、租金、面积和合同数据时，内部经营预测保持未就绪，不生成模拟结果。

目标链路为：

```text
可信数据 → 统一指标 → 描述分析 → 诊断分析 → 机会识别
→ 外部趋势预测 → 招商决策辅助 → 真实内部经营预测
```

## 2. 当前数据链路审计

当前正式数据链路如下：

```text
采集计划 / 手工任务 / CLI
  → crawl_jobs
  → collection_runs（一次完整采集编排）
  → source_runs（按来源记录执行状态）
  → raw_observations（带 scope、来源批次和映射状态）
  → data_snapshots（可发布数据版本）
  → metric_calculation_runs
  → metric_observations（快照指标事实）
  → Dashboard / Brands / Opportunities / Reports / Alerts / Agent
```

兼容链路仍保留：`monitoring_scopes`、`crawl_jobs.brand_id`、`dp_shop_metrics`、`xhs_notes`、旧指标表和旧 API。它们只用于兼容历史调用，不能作为新的正式分析范围条件。

当前数据库的实际审计结果：

| 对象 | 实际情况 | 结论 |
| --- | --- | --- |
| 真实品牌主数据 | `LK001` 瑞幸、`KD001` 库迪、`SB001` 星巴克 | 来自 `brands.brand_id`，可作为品牌实体引用 |
| 试点监测范围 | `scope_a07f9e8937c29771573f48cf`，苏州 × 苏州中心 × 咖啡 | 是正式 `scope_id` |
| 兼容数据集键 | `MALL_906d5b65` | 只表示商场×品类采集数据集，不能当作品牌 |
| 旧范围登记 | 同一城市、项目、品类下曾有 `KD001`、`LK001`、`MALL_906d5b65` 三条旧登记 | 通过 `legacy_scope_links` 归并到一个可信范围，历史数据不删除 |
| 最近成功快照 | `snapshot_506fe24b0e256f0a76b57a2a6b055a98fcc796ca` | 点评成功、小红书 `empty_validated`，质量 B，点评单源 |
| 未归属历史记录 | 点评 74 条、小红书 36 条 | `scope_id` 为空且标记 `legacy_unclassified`，不能自动猜测归属 |

## 3. 核心实体边界

| 实体 | 规范表/字段 | 语义 |
| --- | --- | --- |
| Brand | `brands.brand_id` | 真实品牌主数据，如 `LK001`；不承载采集范围 |
| Store | `stores.store_id` | 真实门店主数据；必须通过人工或可验证映射关联品牌和范围 |
| Monitoring Scope | `trusted_monitoring_scopes.scope_id` | 城市 × 项目（当前字段为 `mall_name`）× 品类的分析边界 |
| Collection Run | `collection_runs.collection_run_id` | 一次完整任务编排，包含多个来源运行 |
| Source Run | `source_runs.source_run_id` | 一次任务中某个来源的执行结果 |
| Snapshot | `data_snapshots.snapshot_id` | 某个范围、某次完整采集结果的可追溯数据版本 |
| Raw Observation | `raw_observations.observation_id` | 单条来源原始观测；`legacy_dataset_key` 是兼容键，`brand_id` 只有确认映射后才写入 |
| Entity Mapping | `brand_id / store_id / entity_mapping_status` | 原始观测到真实实体的关系，待确认时保留为空 |

当前 `trusted_monitoring_scopes.mall_name` 已承担“项目/商场”语义。为避免新增同义字段造成不一致，Phase 1 继续使用该规范字段，并在 API 文档和前端显示为“项目/商场”。后续多组织部署时再引入独立项目主数据表。

## 4. 范围与查询审计

正式可信链路已经在 `raw_observations`、`data_snapshots`、`metric_observations`、机会、报告和告警中使用 `scope_id`。看板查询同时绑定 `scope_id + collection_run_id/snapshot_id`，避免同一项目不同品类混用。

仍需保留并逐步迁移的兼容面：

- `src/backend/brandpulse/api/indicators.py` 仍服务旧 `brand_id + date` 时序接口；不用于新分析中心。
- 旧 `dp_shop_metrics`、`xhs_notes` 和旧指标表仍可被兼容页面读取；正式页面必须使用可信快照表。
- `crawl_jobs.brand_id` 保留历史请求参数语义；新的范围事实由 `crawl_jobs.scope_id → collection_runs.scope_id` 表达。
- `TrustedScopeRepository` 对外返回的 `brand_id` 是兼容别名，实际值来自 `legacy_dataset_key`，前端不得把它展示为真实品牌。

Phase 0 结论：新分析 API 必须只接受明确的 `scope_id`，可选 `snapshot_id` 必须验证属于该范围；所有品牌、门店、来源和指标查询都必须从快照或原始观测的范围关系展开，不能单独用 `brand_id`、城市或项目名称拼接范围。

## 5. 来源、快照和指标口径审计

试点范围当前来源契约为：

| 来源 | 必需 | 空结果 | 当前实际状态 |
| --- | --- | --- | --- |
| 大众点评 WebBridge | 是 | 否 | 最近快照成功并保存 10 条真实观测 |
| 小红书 WebBridge | 否 | 是 | 最近快照 `empty_validated`，不能当作 0 条内容参与综合指标 |

点评和小红书是否来自同一次快照，必须通过：

```text
data_snapshots.snapshot_id
  → data_snapshots.collection_run_id
  → snapshot_source_results.source_run_id
  → source_runs.source_name/status
  → raw_observations.collection_run_id/source_run_id
```

最近成功快照确认是同一 `collection_run_id`，但只包含点评有效观测；小红书是已验证空结果。因此该快照可以作为“点评单源”的正式最低准入结果，但不能标记为多来源完整，也不能补 0 生成小红书指标。

当前指标已经包含快照、范围、来源、质量、样本量和证据字段。指标字典仍缺少最小样本量、是否允许告警、是否允许预测等元数据，这些属于 Phase 2，不在本次 Phase 1 越界实现。

## 6. Phase 1 快照状态机

快照状态定义：

```text
draft → collecting → validating → ready → published
                         ├→ partial
                         ├→ failed
                         └→ rejected

published/ready → expired
published       → superseded
partial/failed  → collecting（重试生成新版本时使用）
```

状态含义：

- `draft`：采集批次已经创建，但还没有开始来源执行。
- `collecting`：至少进入一个来源执行阶段。
- `validating`：来源结果和原始观测已保存，正在计算来源覆盖、质量和新鲜度。
- `ready`：满足正式最低来源契约，可用于正式指标；不代表所有可选来源都有数据。
- `partial`：有可验证数据但必需来源缺失或失败，只能带警告浏览，不能假设完整。
- `published`：明确发布的正式版本；同一范围只保留一个当前 published 版本。
- `failed/rejected`：没有可验证结果或质量门禁拒绝。
- `expired/superseded`：因新版本或新鲜度失效，不再作为默认正式版本。

Phase 1 增加状态历史表并在创建、开始采集、校验、完成和发布时记录状态转换。原有快照数据回填为迁移初始化事件，不改变历史事实。

## 7. Phase 1 数据迁移与兼容方案

新增迁移不删除、不重写以下历史表和原始记录：

- 新增 `snapshot_status_history`，回填每个历史快照的初始状态事件。
- 新增数据库触发器，阻止原始观测、快照、来源结果和指标写入互相矛盾的 `scope_id` / `collection_run_id` / `snapshot_id` 关系。
- 增加可信范围、快照和品类查询索引。
- 新采集在 `collection_run` 创建后立即创建 `draft` 快照；进入采集时转为 `collecting`，来源完成时同步写入 `snapshot_source_results`。
- 历史未归属记录继续保留为 `legacy_unclassified`，不自动绑定到苏州中心咖啡或任何品牌。
- 旧接口和旧字段继续保留；新代码通过兼容别名读取，但不把兼容键当成品牌事实。

迁移失败时 PostgreSQL 事务回滚；应用代码通过旧接口仍可读取历史表。回滚代码时可以停止使用新增状态历史和触发器，但不能删除已产生的可信快照数据。

## 8. 分析中心和预测中心设计基线

Phase 0 只确定产品结构，不在本阶段伪造预测结果。

分析中心第一版：

1. 分析总览：范围、快照、来源覆盖、口碑、评价存量、门店数、趋势和质量警告。
2. 品牌对比：2～5 个已确认品牌的口碑、点评评价、内容、互动、门店覆盖和增量对比。
3. 趋势与证据：相邻可比快照、指标变化、贡献拆解、来源状态和原始观测证据。

机会分析必须展示触发规则、指标证据、来源、快照、质量和人工确认状态，不使用无法解释的总分。

预测中心必须先检查连续可比快照、来源覆盖、映射稳定性和异常快照；没有满足准入条件时只展示“数据未就绪”和缺口，不生成模拟预测。

## 9. 分阶段实施计划

| 阶段 | 交付 |
| --- | --- |
| Phase 0 | 本文审计、实体边界、范围问题、快照状态机、迁移和回滚设计 |
| Phase 1 | 快照提前创建、来源结果及时关联、状态历史、范围一致性触发器、兼容迁移和测试 |
| Phase 2 | 统一指标字典元数据、口碑比较池、趋势和自定义公式正式化 |
| Phase 3 | 统一分析查询层，供前端、报告和 Agent 复用 |
| Phase 4 | 苏州中心咖啡分析总览、品牌对比、趋势与证据三个页面 |
| Phase 5 | 可解释机会规则和招商候选人工复核 |
| Phase 6-8 | 连续可比数据积累、外部增量预测、回测、模型注册与发布 |
| Phase 9 | 获得授权的 POS/客流/租金/面积数据到位后，建设内部经营预测 |

## 10. Phase 0 验收结论

- 已明确真实 `brand_id` 与采集数据集键的区别：`LK001/KD001/SB001` 是品牌，`MALL_906d5b65` 是兼容数据集键。
- 已明确正式范围由 `scope_id` 表达，当前试点范围同时包含城市、项目和品类。
- 已确认点评、小红书和指标是否来自同一次快照必须通过 `snapshot_id → collection_run_id → source_run_id` 判断；最近快照为点评成功、小红书已验证空结果。
- 已发现快照创建时机、状态历史、来源结果即时关联和数据库范围一致性约束四个 Phase 1 底座问题，并给出不破坏历史数据的迁移方式。

## 11. Phase 2～4 实际落地结果

### 11.1 Phase 2：统一指标字典

已新增 `migrations/030_metric_dictionary_phase2.sql` 和 `031_metric_dictionary_corrections.sql`。迁移只扩展/修正指标定义，不重写历史 `metric_observations`，新增元数据包括：

- `formula`：可读的计算公式或计算规则；
- `comparison_scope`：指标允许比较的范围、来源和快照边界；
- `minimum_sample_size`：最小样本门槛；
- `quality_requirements`：来源、样本、可比性等质量要求；
- `allow_alert` / `allow_prediction`：是否允许进入告警或预测流程。

字典已经覆盖存量、增量、质量、竞争和趋势五组指标。当前没有真实小红书、POS、客流、租金或面积数据的指标，只会在 API 中返回 `available=false` 和质量说明，不会写入 0 或生成模拟值。

已有自定义公式通过 `formula:<formula_id>` 纳入分析指标目录。只有 `snapshot_formula_evaluations.status=completed` 的快照绑定结果才会变成可用值；没有快照计算结果时只展示公式定义，不把旧 `custom_formula_values` 的 brand/date 兼容结果混入新分析。当前自定义公式的正式结果是范围级指标，不能被页面伪装成品牌级观测。

### 11.2 Phase 3：统一分析 API

后端新增 `brandpulse.analysis.AnalysisService` 和 `/api/v1/analysis` 查询入口：

```text
GET /api/v1/analysis?scope_id=<scope>&view=overview
GET /api/v1/analysis?scope_id=<scope>&view=comparison&brand_ids=LK001,KD001
GET /api/v1/analysis?scope_id=<scope>&view=trend&metric_key=dp_review_count_stock
GET /api/v1/analysis?scope_id=<scope>&view=evidence&source_name=dianping_webbridge
GET /api/v1/analysis/metrics
```

统一响应始终带有 `scope`、`snapshot`、`filters`、`metrics`、`series`、`ranking`、`comparison`、`evidence`、`quality` 和 `warnings`。品牌查询只接受 `entity_mapping_status=confirmed` 的原始观测；`MALL_*` 兼容数据集键不会被当作品牌。来源失败、跳过或 `empty_validated` 都会保留来源状态，不能按 0 参加综合指标。

变化解释只使用“指标事实变化”和“系统推断边界”表述，未取得因果证据时不输出“导致”或“造成”。原始证据会绑定 `snapshot_id`、`collection_run_id`、来源和观测记录。

### 11.3 Phase 4：分析中心 MVP

前端新增三个真实数据页面：

1. `/analysis` 分析总览：范围、快照、质量、来源覆盖、核心指标、品牌排名、累计评价趋势和原始证据入口；
2. `/analysis/brands` 品牌对比：选择 2～5 个主数据品牌，展示已确认映射的真实对比结果；
3. `/analysis/trends` 趋势与证据：切换指标、查看快照序列、相邻变化和原始观测。

三个页面共用顶部监测范围，筛选状态写入 URL，并实现加载、空数据、错误、来源缺失和低质量状态。没有已确认品牌映射时，品牌排名和对比显示空状态；没有两个可比快照时，趋势显示不可比较，不绘制占位数据。

### 11.4 当前试点真实数据边界

截至本次实施，测试库的苏州 × 苏州中心 × 咖啡范围有 5 个就绪快照，但只有 3 个快照具备可比较的点评新增评价指标；最新快照为点评单源、质量 B，来源覆盖率为 0.5；小红书为 `empty_validated`，原始观测尚无 confirmed 品牌/门店映射。因此范围级点评存量和快照序列可以展示，品牌排名、品牌对比和小红书内容指标必须保持不可用。这是数据事实，不是页面缺陷。

## 12. Phase 5～8 实际落地结果

### 12.1 机会雷达

机会生成服务现在只从 ready/published 快照读取事实，并增加了以下可解释规则：

- `trend_requires_validation`：缺少同口径前序快照时提示“需验证”；
- `source_anomaly`：累计评价数回退或新增评价数为负时标记来源异常；
- `recent_growth` / `continuous_decline`：只有当前与前一快照范围、来源覆盖和数据模式一致且覆盖率达到 80% 才生成；
- 原有的高口碑低评价份额、映射不完整、来源覆盖不完整继续保留。

每条信号携带规则版本、指标证据、来源证据、snapshot_id、质量等级、置信度、信息缺口和推荐动作。生命周期变更写入 `opportunity_signal_events`，并校验状态流转，不允许任意跳过人工复核阶段。

### 12.2 预测准入

新增点评新增评价数预测目标 `dp_review_count_delta`。准入规则为至少 12 个可比较周期、来源覆盖率不低于 80%、采集间隔不超过 7 天、数据模式不切换、目标值不为负；品牌/门店预测还要求稳定实体映射。检查结果写入 `forecast_readiness_checks`，训练前和后台任务执行前各检查一次。

当前真实库检查结果：3 个可比较周期、最低来源覆盖率 50%，所以接口返回 `not_ready`，训练请求返回 409 并说明缺少 9 个周期和覆盖率不足，不创建任务。

### 12.3 外部点评预测 MVP

数据满足准入后，RQ Worker 会读取数据库快照序列，按时间切分最后 3 个周期进行回测，训练一个基础线性模型，并与上一周期值、最近 3 周期均值两个朴素基线比较。输出包括实际值、预测值、MAE、RMSE、WAPE、残差区间、输入快照和模型工件。模型不优于基线时不会进入可发布状态，也不会被标记为内部经营模型。

### 12.4 模型注册和预测中心

新增 `model_registry`、`model_routes` 和 `forecast_results`。训练成功自动登记模型版本；发布时停用同一目标的旧路由但保留旧版本，停用接口可以回收当前路由，满足基础回滚要求。前端新增 /predictions 预测中心，展示准入周期、覆盖率、阻断原因、快照序列、模型指标和发布状态。

### 12.5 对象存储与备份

备份脚本继续先执行 custom-format 归档校验和 SHA-256，再根据 `_OBJECT_STORAGE_BACKEND` 选择本地目录或 S3/MinIO 兼容对象存储。对象存储上传失败会使备份命令失败，不会报告“已备份”但实际未上传。系统配置自检会区分本地存储警告、S3 配置通过和配置缺失。

## 13. 尚未满足的生产条件

- POS、客流、租金、面积、合同和门店主数据仍未授权提供，内部经营预测、坪效、租售比和租户健康度不能执行；
- 小红书当前是已校验空结果，不能参与跨来源综合指标；
- 真实品牌/门店映射仍为 0，品牌级排名、品牌级机会和品牌/门店级预测保持空状态；
- 外部点评预测仍需继续运行采集并达到准入门槛，系统不以降低门槛的方式“完成”预测。
