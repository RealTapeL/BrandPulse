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
