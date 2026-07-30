"""
指标计算层（indicators）

把原始数据加工成可审计的商业指标，是数据层与 Agent/看板之间的计算中间层。

设计原则：
- 只做计算，不做采集：只读 dp_shop_metrics / xhs_notes / brand_heat_daily
- 确定性代码：所有数值由 SQL/Python 算出，禁止 LLM 参与数值计算
- 幂等：按 (stat_date, city, mall_name, entity_type, entity_name) 主键 upsert，可反复重跑
- 可解释：中间量写入 detail JSONB，每个指标都能讲清"怎么算出来的"

模块划分：
- reputation.py  口碑：贝叶斯加权评分
- heat.py        热度：对数加权热度指数
- momentum.py    趋势：周环比动量 + 波动率
- share.py       竞争：声量份额 SOV
- repository.py  brand_indicators_daily 表读写
- pipeline.py    编排入口
"""
