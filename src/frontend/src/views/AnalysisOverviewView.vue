<template>
  <div class="page analysis-page">
    <PageHeader title="分析总览" description="先看结论、范围和证据状态，再进入品牌对比或趋势解释。所有结果来自当前可信快照。">
      <template #actions>
        <DataFreshnessBadge :value="analysis?.snapshot?.observed_at" source="快照" />
        <el-button :loading="loading" @click="load"><el-icon><Refresh /></el-icon>刷新分析</el-button>
        <el-button type="primary" @click="router.push({ path: '/analysis/trends', query: route.query })">查看趋势与证据</el-button>
      </template>
    </PageHeader>

    <el-alert v-if="error" type="error" :closable="false" show-icon class="analysis-alert" :title="error">
      <el-button size="small" @click="load">重新加载</el-button>
    </el-alert>

    <template v-if="loading && !analysis">
      <el-card shadow="never"><el-skeleton :rows="10" animated /></el-card>
    </template>
    <template v-else-if="analysis">
      <section class="context-strip">
        <div><span>当前分析范围</span><strong>{{ scopeLabel }}</strong></div>
        <div><span>快照</span><strong>{{ analysis.snapshot.snapshot_id }}</strong></div>
        <div><span>数据截止</span><strong>{{ formatTime(analysis.snapshot.observed_at) }}</strong></div>
        <div><span>质量</span><el-tag :type="qualityType(analysis.snapshot.quality_grade)" effect="plain">{{ analysis.snapshot.quality_grade || '未评级' }}</el-tag></div>
        <div><span>模式</span><strong>{{ dataModeLabel(analysis.snapshot.data_mode) }}</strong></div>
      </section>

      <el-alert v-if="analysis.warnings.length" type="warning" :closable="false" show-icon class="analysis-alert" title="当前分析边界">
        <ul class="warning-list"><li v-for="warning in analysis.warnings.slice(0, 5)" :key="warning">{{ warning }}</li></ul>
      </el-alert>

      <section class="metric-grid" aria-label="核心分析指标">
        <KpiCard v-for="metric in primaryMetrics" :key="metric.metric_key" :label="metric.display_name" :value="formatMetric(metric)" :note="metric.available ? `${metric.quality_status} · ${metric.unit || '无单位'}` : unavailableNote(metric)" :updated-at="analysis.snapshot.observed_at" source="快照" :icon="metricIcon(metric.metric_group)" />
      </section>

      <section class="analysis-grid">
        <el-card shadow="never" class="panel-card">
          <template #header><div class="panel-heading"><div><h2>品牌排名</h2><p>只纳入当前快照中已确认品牌映射的公开观测。</p></div><el-button link type="primary" @click="router.push({ path: '/analysis/brands', query: route.query })">进入品牌对比</el-button></div></template>
          <div v-if="analysis.ranking.length" class="table-scroll">
            <el-table :data="analysis.ranking.slice(0, 10)" size="small">
              <el-table-column type="index" label="#" width="52" />
              <el-table-column prop="brand_name" label="品牌" min-width="140" show-overflow-tooltip />
              <el-table-column label="贝叶斯口碑" width="120"><template #default="{ row }">{{ number(row.weighted_score, 2) }}</template></el-table-column>
              <el-table-column label="累计评价" width="110"><template #default="{ row }">{{ number(row.review_count) }}</template></el-table-column>
              <el-table-column label="点评份额" width="110"><template #default="{ row }">{{ percent(row.review_share) }}</template></el-table-column>
            </el-table>
          </div>
          <EmptyState v-else icon="Shop" title="暂无可比品牌" description="主数据品牌不会自动等于快照中的品牌。请在数据中心完成原始观测与真实品牌、门店的确认映射。"><el-button type="primary" link @click="router.push('/data?tab=matching')">处理实体映射</el-button></EmptyState>
        </el-card>

        <el-card shadow="never" class="panel-card">
          <template #header><div class="panel-heading"><div><h2>累计评价趋势</h2><p>仅展示同一范围的真实快照序列；无因果判断。</p></div><el-tag type="info" effect="plain">{{ trendAvailability }}</el-tag></div></template>
          <EChart v-if="analysis.trend_available" :option="trendOption" height="280px" />
          <EmptyState v-else icon="TrendCharts" title="趋势暂不可比较" description="至少需要两个同范围、同来源、时间间隔合规且质量可用的快照；当前页面不会绘制模拟趋势。" />
        </el-card>
      </section>

      <section class="analysis-grid lower-grid">
        <el-card shadow="never" class="panel-card">
          <template #header><div class="panel-heading"><div><h2>来源覆盖</h2><p>失败、跳过和已验证空结果都不会按 0 参与综合指标。</p></div></div></template>
          <div class="source-list">
            <div v-for="source in sourceResults" :key="source.source_name" class="source-row">
              <div><strong>{{ sourceLabel(source.source_name) }}</strong><span>{{ source.required ? '必需来源' : '可选来源' }}</span></div>
              <el-tag :type="sourceType(source.status)" effect="plain" size="small">{{ sourceStatus(source.status) }}</el-tag>
            </div>
          </div>
        </el-card>
        <el-card shadow="never" class="panel-card">
          <template #header><div class="panel-heading"><div><h2>原始证据</h2><p>当前快照中可回溯的真实观测，不是品牌结论。</p></div><el-button link type="primary" @click="router.push({ path: '/analysis/trends', query: route.query })">查看全部</el-button></div></template>
          <div v-if="analysis.evidence.length" class="evidence-list">
            <div v-for="item in analysis.evidence.slice(0, 5)" :key="item.observation_id" class="evidence-row">
              <div><strong>{{ item.payload?.shop_name || item.payload?.title || item.source_record_key }}</strong><span>{{ sourceLabel(item.source_name) }} · {{ item.entity_mapping_status }}</span></div>
              <el-tag :type="item.entity_mapping_status === 'confirmed' ? 'success' : 'warning'" effect="plain" size="small">{{ item.entity_mapping_status === 'confirmed' ? '已映射' : '待确认' }}</el-tag>
            </div>
          </div>
          <EmptyState v-else icon="Document" title="暂无原始证据" description="当前快照没有可展示的接受记录。" />
        </el-card>
      </section>
    </template>
    <EmptyState v-else icon="DataAnalysis" title="分析数据未就绪" description="请先选择监测范围，并完成一次真实采集与快照校验。" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import KpiCard from '../components/KpiCard.vue'
import EChart from '../components/EChart.vue'
import EmptyState from '../components/EmptyState.vue'
import DataFreshnessBadge from '../components/DataFreshnessBadge.vue'
import { fetchAnalysis } from '../api/analysis'
import { useScopeStore } from '../stores/scope'

const route = useRoute()
const router = useRouter()
const scopeStore = useScopeStore()
const analysis = ref(null)
const loading = ref(false)
const error = ref('')

const scopeLabel = computed(() => analysis.value?.scope ? [analysis.value.scope.city, analysis.value.scope.mall_name, analysis.value.scope.category].join(' · ') : scopeStore.label)
const primaryMetrics = computed(() => (analysis.value?.metrics || []).slice(0, 6))
const sourceResults = computed(() => analysis.value?.snapshot?.source_results || analysis.value?.snapshot?.source_coverage?.sources || [])
const trendAvailability = computed(() => analysis.value?.trend_available ? '可比较' : '不可比较')
const trendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 42, right: 18, top: 18, bottom: 30 },
  xAxis: { type: 'category', data: (analysis.value?.series || []).map((item) => formatDate(item.observed_at)), axisLabel: { color: '#7b8da3' } },
  yAxis: { type: 'value', name: '条', splitLine: { lineStyle: { color: '#edf1f5' } } },
  series: [{ type: 'line', smooth: false, connectNulls: false, data: (analysis.value?.series || []).map((item) => item.value), symbolSize: 7, itemStyle: { color: '#2676e8' }, lineStyle: { color: '#2676e8', width: 2 } }],
}))

async function load() {
  loading.value = true
  error.value = ''
  try {
    await scopeStore.load()
    const queryScope = String(route.query.scope_id || '')
    if (queryScope && scopeStore.items.some((item) => item.scope_id === queryScope)) scopeStore.setCurrent(queryScope)
    if (!scopeStore.currentId) { analysis.value = null; return }
    syncUrl()
    analysis.value = await fetchAnalysis({ scope_id: scopeStore.currentId, view: 'overview', limit: 30 })
  } catch (err) {
    error.value = String(err?.response?.data?.detail || err?.message || err)
  } finally { loading.value = false }
}

function syncUrl() {
  if (route.query.scope_id !== scopeStore.currentId) router.replace({ query: { ...route.query, scope_id: scopeStore.currentId } })
}
function formatMetric(metric) {
  if (!metric?.available) return '—'
  const value = Number(metric.value)
  if (!Number.isFinite(value)) return '—'
  return metric.unit === '比例' ? `${(value * 100).toFixed(1)}%` : value.toLocaleString('zh-CN', { maximumFractionDigits: metric.unit === '分' ? 2 : 0 })
}
function unavailableNote(metric) { return metric?.quality_status === 'unavailable' ? '当前来源或样本不足' : '证据不完整' }
function number(value, digits = 0) { return Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits }) : '—' }
function percent(value) { return Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : '—' }
function formatTime(value) { return value ? new Date(value).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' }) : '—' }
function formatDate(value) { return value ? new Date(value).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) : '—' }
function qualityType(value) { return ({ A: 'success', B: 'success', C: 'warning', D: 'danger', F: 'danger' })[value] || 'info' }
function dataModeLabel(value) { return ({ multi_source: '多来源', dianping_single_source: '点评单源', single_source: '单源', raw_only: '原始数据' })[value] || '未定义' }
function metricIcon(group) { return ({ stock: 'DataAnalysis', activity: 'TrendCharts', quality: 'CircleCheck', competition: 'Histogram', trend: 'TrendCharts' })[group] || 'DataAnalysis' }
function sourceLabel(value) { return ({ dianping_webbridge: '大众点评', xiaohongshu_webbridge: '小红书', amap: '高德' })[value] || value || '未知来源' }
function sourceStatus(value) { return ({ success: '成功', empty_validated: '已验证为空', failed: '失败', skipped: '跳过', stale: '已过期' })[value] || value || '未执行' }
function sourceType(value) { return ({ success: 'success', empty_validated: 'warning', failed: 'danger', skipped: 'info', stale: 'warning' })[value] || 'info' }
watch(() => scopeStore.currentId, (next, previous) => { if (next && next !== previous && !loading.value) load() })
watch(() => route.query.scope_id, (next, previous) => { if (next && next !== previous && !loading.value) load() })
onMounted(load)
</script>

<style scoped>
.analysis-page { min-width: 0; }
.analysis-alert { margin-bottom: 16px; }
.context-strip { display: grid; grid-template-columns: 1.4fr 1.5fr 1fr .6fr 1fr; gap: 1px; margin-bottom: 16px; overflow: hidden; border: 1px solid var(--bp-card-border); border-radius: var(--bp-radius-md); background: var(--bp-card-border); }
.context-strip > div { display: flex; min-width: 0; flex-direction: column; gap: 6px; padding: 13px 15px; background: var(--bp-surface); }
.context-strip span { color: var(--bp-text-muted); font-size: 12px; }
.context-strip strong { overflow: hidden; color: var(--bp-text-strong); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.metric-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.analysis-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, .85fr); gap: 18px; margin-bottom: 18px; }
.lower-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.panel-card { min-width: 0; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
h2 { margin: 0; color: var(--bp-text-strong); font-size: 16px; }
.panel-heading p { margin: 5px 0 0; color: var(--bp-text-muted); font-size: 12px; line-height: 1.5; }
.warning-list { margin: 0; padding-left: 18px; line-height: 1.7; }
.source-list, .evidence-list { display: flex; flex-direction: column; }
.source-row, .evidence-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid #edf1f5; }
.source-row:last-child, .evidence-row:last-child { border-bottom: 0; }
.source-row div, .evidence-row div { display: flex; min-width: 0; flex-direction: column; gap: 4px; }
.source-row strong, .evidence-row strong { overflow: hidden; color: var(--bp-text-primary); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.source-row span, .evidence-row span { color: var(--bp-text-muted); font-size: 12px; }
@media (max-width: 1280px) { .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } .context-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 900px) { .analysis-grid, .lower-grid { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .context-strip { grid-template-columns: 1fr 1fr; } }
</style>
