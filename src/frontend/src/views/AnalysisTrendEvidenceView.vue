<template>
  <div class="page analysis-page">
    <PageHeader title="趋势与证据" description="查看指标随快照的真实变化，并直接回溯来源、快照和原始观测。没有可比较周期时不输出趋势结论。">
      <template #actions><DataFreshnessBadge :value="analysis?.snapshot?.observed_at" source="快照" /><el-button :loading="loading" @click="load"><el-icon><Refresh /></el-icon>刷新</el-button></template>
    </PageHeader>

    <el-card shadow="never" class="filter-card">
      <div class="filter-row"><div class="filter-field"><label>趋势指标</label><el-select v-model="metricKey" class="metric-select" @change="onMetricChange"><el-option v-for="metric in trendMetrics" :key="metric.metric_key" :label="metric.display_name" :value="metric.metric_key" /></el-select></div><div class="filter-summary"><span>范围</span><strong>{{ scopeLabel }}</strong></div></div>
    </el-card>

    <el-alert v-if="error" type="error" :closable="false" show-icon class="analysis-alert" :title="error"><el-button size="small" @click="load">重试</el-button></el-alert>
    <template v-if="analysis">
      <section class="context-strip"><div><span>快照</span><strong>{{ analysis.snapshot.snapshot_id }}</strong></div><div><span>数据截止</span><strong>{{ formatTime(analysis.snapshot.observed_at) }}</strong></div><div><span>质量</span><el-tag :type="qualityType(analysis.snapshot.quality_grade)" effect="plain">{{ analysis.snapshot.quality_grade || '未评级' }}</el-tag></div><div><span>证据条数</span><strong>{{ analysis.evidence.length }}</strong></div></section>
      <el-alert v-if="analysis.warnings.length" type="warning" :closable="false" show-icon class="analysis-alert" title="趋势解释边界"><ul class="warning-list"><li v-for="warning in analysis.warnings.slice(0, 6)" :key="warning">{{ warning }}</li></ul></el-alert>

      <section class="trend-grid">
        <el-card shadow="never" class="panel-card trend-panel">
          <template #header><div class="panel-heading"><div><h2>{{ analysis.metric?.display_name || metricKey }}</h2><p>{{ analysis.metric?.description || '指标定义未找到' }} · {{ analysis.metric?.formula || '无公式说明' }}</p></div><el-tag type="info" effect="plain">{{ analysis.series.length }} 个快照</el-tag></div></template>
          <EChart v-if="analysis.trend_available" :option="trendOption" height="330px" />
          <EmptyState v-else icon="TrendCharts" title="没有可绘制的趋势" description="需要至少两个同范围、同来源、时间间隔合规且质量可比较的快照。" />
        </el-card>
        <el-card shadow="never" class="panel-card">
          <template #header><div class="panel-heading"><div><h2>相邻周期变化</h2><p>这是指标事实变化，不是因果结论。</p></div></div></template>
          <template v-if="analysis.comparison?.available">
            <div class="comparison-value"><span>变化量</span><strong :class="changeClass">{{ signedNumber(analysis.comparison.delta) }}</strong></div>
            <div class="comparison-meta"><span>前一快照</span><strong>{{ number(analysis.comparison.previous_value) }}</strong></div>
            <div class="comparison-meta"><span>当前快照</span><strong>{{ number(analysis.comparison.current_value) }}</strong></div>
            <div class="comparison-meta"><span>变化率</span><strong>{{ percent(analysis.comparison.growth_rate) }}</strong></div>
            <el-alert type="info" :closable="false" title="系统推断边界：当前只说明两个可比较快照的数值变化，未证明变化原因。" />
          </template>
          <EmptyState v-else icon="Warning" title="暂无可比较变化" :description="analysis.comparison?.reason || '当前指标缺少相邻可比快照。'" />
        </el-card>
      </section>

      <section class="evidence-section">
        <el-card shadow="never" class="panel-card">
          <template #header><div class="panel-heading"><div><h2>快照序列</h2><p>每个点都绑定 snapshot_id、来源、质量状态和证据。</p></div></div></template>
          <div class="table-scroll"><el-table :data="analysis.series" size="small"><el-table-column label="时间" width="150"><template #default="{ row }">{{ formatTime(row.observed_at) }}</template></el-table-column><el-table-column prop="snapshot_id" label="snapshot_id" min-width="270" show-overflow-tooltip /><el-table-column label="指标值" width="120"><template #default="{ row }">{{ row.value === null ? '不可用' : number(row.value) }}</template></el-table-column><el-table-column prop="quality_status" label="质量状态" width="130" /><el-table-column prop="source_name" label="来源" width="170" /></el-table></div>
          <EmptyState v-if="!analysis.series.length" icon="Document" title="暂无指标快照记录" />
        </el-card>
        <el-card shadow="never" class="panel-card">
          <template #header><div class="panel-heading"><div><h2>原始观测证据</h2><p>来自当前 snapshot 对应 collection_run；未确认映射仍保留原始事实。</p></div><el-tag type="info" effect="plain">{{ analysis.evidence.length }} 条</el-tag></div></template>
          <div class="table-scroll"><el-table :data="analysis.evidence" size="small"><el-table-column label="观测对象" min-width="190" show-overflow-tooltip><template #default="{ row }">{{ row.payload?.shop_name || row.payload?.title || row.source_record_key }}</template></el-table-column><el-table-column prop="source_name" label="来源" width="155" /><el-table-column prop="observed_date" label="观测日期" width="125" /><el-table-column prop="entity_mapping_status" label="实体映射" width="120" /><el-table-column label="原始链接" width="100"><template #default="{ row }"><el-link v-if="row.source_url" :href="row.source_url" target="_blank" type="primary">打开</el-link><span v-else>—</span></template></el-table-column></el-table></div>
          <EmptyState v-if="!analysis.evidence.length" icon="Document" title="暂无原始观测证据" description="当前快照对应来源没有接受记录。" />
        </el-card>
      </section>
    </template>
    <EmptyState v-else icon="TrendCharts" title="趋势数据未就绪" description="请先选择监测范围，并等待真实快照完成校验。" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import EChart from '../components/EChart.vue'
import EmptyState from '../components/EmptyState.vue'
import DataFreshnessBadge from '../components/DataFreshnessBadge.vue'
import { fetchAnalysis, fetchAnalysisMetrics } from '../api/analysis'
import { useScopeStore } from '../stores/scope'

const route = useRoute(); const router = useRouter(); const scopeStore = useScopeStore()
const analysis = ref(null); const metrics = ref([]); const loading = ref(false); const error = ref('')
const metricKey = ref(String(route.query.metric || 'dp_review_count_stock'))
const scopeLabel = computed(() => analysis.value?.scope ? [analysis.value.scope.city, analysis.value.scope.mall_name, analysis.value.scope.category].join(' · ') : scopeStore.label)
const trendMetrics = computed(() => metrics.value.filter((metric) => ['stock', 'activity', 'trend', 'custom'].includes(metric.metric_group)))
const trendOption = computed(() => ({ tooltip: { trigger: 'axis' }, grid: { left: 48, right: 18, top: 20, bottom: 35 }, xAxis: { type: 'category', data: (analysis.value?.series || []).map((item) => formatDate(item.observed_at)), axisLabel: { color: '#7b8da3' } }, yAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf1f5' } } }, series: [{ type: 'line', data: (analysis.value?.series || []).map((item) => item.value), connectNulls: false, symbolSize: 7, itemStyle: { color: '#2676e8' }, lineStyle: { color: '#2676e8', width: 2 } }] }))
const changeClass = computed(() => Number(analysis.value?.comparison?.delta || 0) >= 0 ? 'positive' : 'negative')

async function load() {
  loading.value = true; error.value = ''
  try {
    await scopeStore.load()
    if (route.query.scope_id && scopeStore.items.some((item) => item.scope_id === route.query.scope_id)) scopeStore.setCurrent(String(route.query.scope_id))
    metrics.value = (await fetchAnalysisMetrics()).items || []
    if (!scopeStore.currentId) { analysis.value = null; return }
    syncUrl()
    analysis.value = await fetchAnalysis({ scope_id: scopeStore.currentId, view: 'trend', metric_key: metricKey.value, limit: 30 })
  } catch (err) { error.value = String(err?.response?.data?.detail || err?.message || err) } finally { loading.value = false }
}
async function onMetricChange() { syncUrl(); await load() }
function syncUrl() { router.replace({ query: { ...route.query, scope_id: scopeStore.currentId, metric: metricKey.value } }) }
function number(value, digits = 2) { return Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits }) : '—' }
function signedNumber(value) { return Number.isFinite(Number(value)) ? `${Number(value) > 0 ? '+' : ''}${number(value, 2)}` : '—' }
function percent(value) { return Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : '—' }
function formatTime(value) { return value ? new Date(value).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' }) : '—' }
function formatDate(value) { return value ? new Date(value).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) : '—' }
function qualityType(value) { return ({ A: 'success', B: 'success', C: 'warning', D: 'danger', F: 'danger' })[value] || 'info' }
watch(() => scopeStore.currentId, (next, previous) => { if (next && next !== previous && !loading.value) load() })
watch(() => route.query.metric, (next, previous) => { if (next && next !== previous && next !== metricKey.value) { metricKey.value = String(next); load() } })
onMounted(load)
</script>

<style scoped>
.analysis-page { min-width: 0; }
.filter-card { margin-bottom: 16px; }
.filter-row { display: flex; align-items: end; gap: 24px; flex-wrap: wrap; }
.filter-field { display: flex; min-width: min(360px, 100%); flex-direction: column; gap: 7px; }
.filter-field label, .filter-summary span { color: var(--bp-text-muted); font-size: 12px; }
.metric-select { width: min(360px, 100%); }
.filter-summary { display: flex; flex-direction: column; gap: 7px; }
.filter-summary strong { color: var(--bp-text-strong); font-size: 13px; }
.analysis-alert { margin-bottom: 16px; }
.context-strip { display: grid; grid-template-columns: 2fr 1.4fr .7fr .7fr; gap: 1px; margin-bottom: 16px; overflow: hidden; border: 1px solid var(--bp-card-border); border-radius: var(--bp-radius-md); background: var(--bp-card-border); }
.context-strip > div { display: flex; min-width: 0; flex-direction: column; gap: 6px; padding: 13px 15px; background: var(--bp-surface); }
.context-strip span { color: var(--bp-text-muted); font-size: 12px; }
.context-strip strong { overflow: hidden; color: var(--bp-text-strong); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.trend-grid, .evidence-section { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(300px, .7fr); gap: 18px; margin-bottom: 18px; }
.evidence-section { grid-template-columns: 1fr; }
.panel-card { min-width: 0; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
h2 { margin: 0; color: var(--bp-text-strong); font-size: 16px; }
.panel-heading p { max-width: 720px; margin: 5px 0 0; color: var(--bp-text-muted); font-size: 12px; line-height: 1.55; }
.warning-list { margin: 0; padding-left: 18px; line-height: 1.7; }
.comparison-value { display: flex; flex-direction: column; gap: 6px; padding: 10px 0 20px; border-bottom: 1px solid #edf1f5; }
.comparison-value span, .comparison-meta span { color: var(--bp-text-muted); font-size: 12px; }
.comparison-value strong { font-size: 32px; line-height: 1.2; }
.positive { color: #1f9d68; }.negative { color: #d45151; }
.comparison-meta { display: flex; align-items: center; justify-content: space-between; padding: 14px 0; border-bottom: 1px solid #edf1f5; }
.comparison-meta strong { color: var(--bp-text-strong); font-size: 14px; }
.comparison-meta + .el-alert { margin-top: 18px; }
@media (max-width: 900px) { .trend-grid { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .context-strip { grid-template-columns: 1fr 1fr; } .filter-field, .metric-select { width: 100%; min-width: 0; } }
</style>
