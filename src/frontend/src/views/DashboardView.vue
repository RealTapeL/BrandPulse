<template>
  <div class="page workbench-page">
    <PageHeader title="工作台" :description="scopeDescription">
      <template #actions>
        <DataFreshnessBadge :value="data?.crawl_date" source="大众点评" />
        <DataFreshnessBadge :value="xhsLatestDate" source="小红书" />
        <el-button :loading="loading" @click="reload"><el-icon><Refresh /></el-icon>刷新数据</el-button>
        <el-button type="primary" :disabled="!scopeStore.currentId" @click="router.push('/automation?tab=collection')"><el-icon><Timer /></el-icon>发起采集</el-button>
      </template>
    </PageHeader>

    <el-alert v-if="error" class="workbench-error" type="error" :title="`工作台数据加载失败：${error}`" :closable="false" show-icon>
      <template #default><el-button size="small" @click="reload">重新加载</el-button></template>
    </el-alert>

    <template v-else-if="loading && !data"><el-card shadow="never"><el-skeleton :rows="10" animated /></el-card></template>
    <template v-else-if="data">
      <section class="focus-section">
        <el-card shadow="never" class="focus-card">
          <div class="focus-card__heading"><div><span class="eyebrow">TODAY FOCUS</span><h2>今日需要关注</h2><p>信号基于当前范围的真实快照与数据质量记录生成，不以缺失数据推断结论。</p></div><el-button text type="primary" @click="router.push('/opportunities')">查看机会雷达 <el-icon><ArrowRight /></el-icon></el-button></div>
          <div v-if="focusItems.length" class="focus-list">
            <article v-for="item in focusItems" :key="item.key" class="focus-item">
              <el-tag :type="signalType(item.type)" effect="plain" size="small">{{ item.type }}</el-tag>
              <div class="focus-item__copy"><strong>{{ item.entity }}</strong><span>{{ item.rule }} · {{ item.detail }}</span></div>
              <el-button link type="primary" @click="router.push(item.actionPath)">{{ item.action }}</el-button>
            </article>
          </div>
          <EmptyState v-else icon="CircleCheck" title="当前没有需要处理的显著信号" description="数据到位后，工作台会从竞争快照、质量问题和来源新鲜度中生成关注项。" />
        </el-card>
      </section>

      <section class="kpi-grid" aria-label="核心指标">
        <KpiCard label="点评观测门店" :value="observedStoreCount" note="当前快照通过校验的公开门店" :updated-at="data.crawl_date" source="点评" icon="Shop" />
        <KpiCard label="点评累计评价" :value="reviewStock" note="公开累计存量，不代表近期热度" :updated-at="data.stat_date" source="点评" icon="Document" />
        <KpiCard label="平均贝叶斯口碑" :value="averageScore" note="同范围公开门店比较池" :updated-at="data.stat_date" source="点评" icon="Star" />
        <KpiCard label="来源覆盖率" :value="sourceCoverage" :note="sourceCoverageNote" :updated-at="data.stat_date" source="快照" icon="Connection" />
      </section>

      <section class="main-grid">
        <el-card shadow="never" class="competition-card">
          <template #header><div class="card-title-row"><div><h2>点评竞争观测</h2><p>横轴为贝叶斯口碑，纵轴为点评评价份额，气泡面积为累计评价数。仅基于当前快照的单一来源，不等同于近期热度或经营表现。</p></div><el-tag type="info" effect="plain">门店线索</el-tag></div></template>
          <EChart v-if="comparisonRows.length" :option="reviewShareOption" height="390px" />
          <EmptyState v-else title="暂无可用的单源竞争观测" description="需要完成点评采集、快照校验与口碑指标计算后才能展示；未映射记录不会成为正式品牌指标。"><el-button type="primary" link @click="router.push('/data?tab=overview')">查看数据就绪情况</el-button></EmptyState>
        </el-card>

        <el-card shadow="never" class="opportunity-card">
          <template #header><div class="card-title-row"><div><h2>机会雷达</h2><p>按当前快照的相对位置排序。</p></div><el-button link type="primary" @click="router.push('/opportunities')">全部</el-button></div></template>
          <div v-if="opportunities.length" class="opportunity-list"><article v-for="item in opportunities.slice(0, 5)" :key="item.key" class="opportunity-item"><el-tag :type="signalType(item.type)" size="small">{{ item.type }}</el-tag><div><strong>{{ item.entity }}</strong><p>{{ item.rule }}</p><span>{{ item.detail }}</span></div></article></div>
          <EmptyState v-else icon="Compass" title="暂无可识别机会" description="当前范围的指标量不足，或没有触发已配置的相对位置规则。" />
        </el-card>
      </section>

      <section class="main-grid lower-grid">
        <el-card shadow="never" class="trend-card">
          <template #header><div class="card-title-row"><div><h2>当前动量与趋势可用性</h2><p>仅展示指标表已实际产出的周环比动量；没有历史序列时不绘制伪趋势。</p></div><el-button link type="primary" @click="router.push('/brands')">查看品牌库</el-button></div></template>
          <EChart v-if="momentumRows.length" :option="momentumOption" height="268px" />
          <EmptyState v-else icon="TrendCharts" title="趋势数据尚未积累" description="当前只具备最新快照或没有有效周环比动量。连续采集并生成多个指标日后可进行趋势比较。" />
        </el-card>

        <el-card shadow="never" class="content-card">
          <template #header><div class="card-title-row"><div><h2>热门内容</h2><p>按已采集点赞数排序的公开内容。</p></div><el-button link type="primary" @click="router.push('/data?tab=tables')">浏览原始数据</el-button></div></template>
          <div v-if="data.xhs_notes.length" class="content-list"><article v-for="note in data.xhs_notes.slice(0, 4)" :key="`${note.title}-${note.publish_time}`" class="content-item"><div class="content-item__main"><a v-if="note.note_url" :href="note.note_url" target="_blank" rel="noreferrer">{{ note.title || '未命名笔记' }}</a><strong v-else>{{ note.title || '未命名笔记' }}</strong><span>{{ note.author_name || '未知作者' }} · {{ note.publish_time || '发布时间未提供' }}</span></div><div class="content-item__likes"><el-icon><StarFilled /></el-icon>{{ formatNumber(note.likes) }}</div></article></div>
          <EmptyState v-else icon="Document" title="暂无小红书内容" description="当前范围没有可展示的公开内容采集记录。" />
        </el-card>
      </section>

      <section class="tasks-section">
        <div class="section-heading"><div><h2>待处理事项</h2><p>事项会保留来源证据、负责人和处理结果；不是仅展示一个通知数字。</p></div><el-button text type="primary" @click="router.push('/automation?tab=cases')">进入事项闭环 <el-icon><ArrowRight /></el-icon></el-button></div>
        <div class="task-grid"><el-card shadow="never" class="task-card"><el-icon><Finished /></el-icon><div><strong>{{ openCaseCount }} 个待处理事项</strong><p>{{ openCaseCount ? '请在事项闭环中分派、记录处置并反馈有效性。' : '当前没有开放的业务事项。' }}</p></div><el-button link type="primary" @click="router.push('/automation?tab=cases')">查看</el-button></el-card><el-card shadow="never" class="task-card"><el-icon><Timer /></el-icon><div><strong>{{ activeScheduleCount }} 个启用采集计划</strong><p>{{ activeScheduleCount ? '可在自动化中心查看最近执行结果。' : '尚未启用自动采集计划。' }}</p></div><el-button link type="primary" @click="router.push('/automation?tab=collection')">管理</el-button></el-card><el-card shadow="never" class="task-card"><el-icon><Bell /></el-icon><div><strong>{{ enabledAlertCount }} 条可信范围告警</strong><p>{{ enabledAlertCount ? '请检查投递记录，确认通知渠道可用。' : '尚未配置启用中的可信范围告警。' }}</p></div><el-button link type="primary" @click="router.push('/automation?tab=alerts')">配置</el-button></el-card></div>
      </section>
    </template>
    <EmptyState v-else title="暂无已登记监测范围" description="请先在自动化中心登记范围并完成一次真实数据采集。"><el-button type="primary" @click="router.push('/automation?tab=collection')">前往采集计划</el-button></EmptyState>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import EChart from '../components/EChart.vue'
import PageHeader from '../components/PageHeader.vue'
import KpiCard from '../components/KpiCard.vue'
import DataFreshnessBadge from '../components/DataFreshnessBadge.vue'
import EmptyState from '../components/EmptyState.vue'
import { buildMomentumOption, buildReviewShareOption } from '../components/dashboard/chartOptions'
import { fetchDashboard } from '../api/dashboard'
import { fetchAlerts } from '../api/alerts'
import { fetchCrawlSchedules } from '../api/monitoring'
import { fetchOpportunities } from '../api/opportunities'
import { fetchCases } from '../api/cases'
import { useScopeStore } from '../stores/scope'
import { average, formatNumber, formatPercent } from '../utils/insights'

const router = useRouter()
const scopeStore = useScopeStore()
const data = ref(null)
const schedules = ref([])
const alerts = ref([])
const opportunitySignals = ref([])
const cases = ref([])
const loading = ref(false)
const error = ref('')

const scopeDescription = computed(() => scopeStore.current ? `${scopeStore.label} 的品牌竞争态势、数据状态与待处理事项。` : '选择一个城市、商场和品类范围后查看真实数据。')
const xhsLatestDate = computed(() => (data.value?.xhs_notes || []).reduce((latest, note) => (note.crawl_date || '') > latest ? note.crawl_date : latest, ''))
const opportunities = computed(() => opportunitySignals.value.map(toOpportunityItem))
const focusItems = computed(() => opportunities.value.slice(0, 5))
const averageScore = computed(() => { const value = average(data.value?.indicators || [], 'weighted_score'); return value === null ? '-' : formatNumber(value, 2) })
const metricByKey = computed(() => Object.fromEntries((data.value?.metric_summary || []).map((item) => [item.metric_key, item])))
const metricValue = (key) => metricByKey.value[key]?.value
const observedStoreCount = computed(() => formatNumber(metricValue('dp_store_count_observed') ?? data.value?.dp_shops?.length))
const reviewStock = computed(() => formatNumber(metricValue('dp_review_count_stock')))
const sourceCoverage = computed(() => formatPercent(metricValue('source_coverage_ratio')))
const sourceCoverageNote = computed(() => {
  const results = data.value?.source_results || []
  const successful = results.filter((item) => item.status === 'success').map((item) => item.source_name)
  return successful.length ? `已成功：${successful.join('、')}` : '暂无成功来源'
})
const comparisonRows = computed(() => (data.value?.indicators || []).filter((item) => (
  Number.isFinite(Number(item.weighted_score)) && Number.isFinite(Number(item.sov)) && Number.isFinite(Number(item.review_count))
)))
const reviewShareOption = computed(() => buildReviewShareOption(comparisonRows.value))
const momentumRows = computed(() => (data.value?.indicators || []).filter((item) => Number.isFinite(Number(item.wow_momentum))))
const momentumOption = computed(() => buildMomentumOption(momentumRows.value))
const openCaseCount = computed(() => cases.value.filter((item) => !['resolved', 'closed'].includes(item.status)).length)
const activeScheduleCount = computed(() => schedules.value.filter((item) => item.enabled).length)
const enabledAlertCount = computed(() => alerts.value.filter((item) => item.enabled && item.rule_scope_status === 'trusted_scope').length)

function signalType(type) { return ({ 机会: 'success', 风险: 'warning', 信号: 'info', 数据问题: 'danger' })[type] || 'info' }
function toOpportunityItem(signal) {
  const type = ({ opportunity: '机会', risk: '风险', data_quality: '数据问题', information: '信号' })[signal.signal_class] || '信号'
  const mappingIssue = signal.signal_type === 'data_mapping_incomplete'
  const sourceIssue = signal.signal_type === 'source_coverage_incomplete'
  return {
    key: signal.signal_id,
    entity: signal.entity_name,
    type,
    rule: signal.trigger_rule,
    detail: signal.recommended_action || '请查看信号证据后由业务人员确认下一步。',
    action: mappingIssue ? '处理原始映射' : sourceIssue ? '查看快照来源' : '查看机会雷达',
    actionPath: mappingIssue ? '/data?tab=matching' : sourceIssue ? '/data?tab=snapshots' : '/opportunities',
    priority: type === '数据问题' ? 1000 : Number(signal.confidence || 0),
  }
}
async function reload() {
  loading.value = true
  error.value = ''
  try {
    await scopeStore.load()
    if (!scopeStore.currentId) { data.value = null; return }
    const [dashboard, crawlSchedules, alertRules, signalResult, caseResult] = await Promise.all([
      fetchDashboard(scopeStore.currentId), fetchCrawlSchedules().catch(() => ({ items: [] })), fetchAlerts().catch(() => []), fetchOpportunities({ scopeId: scopeStore.currentId }).catch(() => ({ items: [] })), fetchCases().catch(() => ({ items: [] })),
    ])
    data.value = dashboard; schedules.value = crawlSchedules.items || []; alerts.value = Array.isArray(alertRules) ? alertRules : []; opportunitySignals.value = signalResult.items || []; cases.value = caseResult.items || []
  } catch (err) { error.value = String(err?.response?.data?.detail || err?.message || err) } finally { loading.value = false }
}
watch(() => scopeStore.currentId, (next, previous) => { if (next && next !== previous && !loading.value) reload() })
onMounted(reload)
</script>

<style scoped>
.workbench-error { margin-bottom: 16px; }.focus-section { margin-bottom: 18px; }.focus-card { border-color: #dce8f7; background: #fbfdff; }.focus-card__heading, .card-title-row, .section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }.eyebrow { display: block; margin-bottom: 5px; color: var(--bp-primary); font-size: 11px; font-weight: 700; letter-spacing: .09em; }h2 { margin: 0; color: var(--bp-text-strong); font-size: 17px; line-height: 1.35; }p { margin: 5px 0 0; color: var(--bp-text-muted); font-size: 12px; line-height: 1.55; }.focus-list { margin-top: 16px; border-top: 1px solid #edf2f7; }.focus-item { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 13px 0; border-bottom: 1px solid #edf2f7; }.focus-item:last-child { border-bottom: 0; padding-bottom: 0; }.focus-item__copy { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; min-width: 0; }.focus-item__copy strong { color: var(--bp-text-strong); font-size: 13px; }.focus-item__copy span { color: var(--bp-text-secondary); font-size: 12px; line-height: 1.5; }.kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }.main-grid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(340px, .9fr); gap: 18px; align-items: stretch; margin-bottom: 18px; }.lower-grid { grid-template-columns: minmax(0, 1.15fr) minmax(340px, .85fr); }.competition-card, .opportunity-card, .trend-card, .content-card { min-width: 0; }.card-title-row h2 { font-size: 16px; }.opportunity-list, .content-list { display: flex; flex-direction: column; }.opportunity-item { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: flex-start; gap: 10px; padding: 12px 0; border-bottom: 1px solid #edf1f5; }.opportunity-item:first-child { padding-top: 0; }.opportunity-item:last-child { border-bottom: 0; padding-bottom: 0; }.opportunity-item strong { color: var(--bp-text-strong); font-size: 13px; }.opportunity-item p { margin: 2px 0; color: #54708f; font-size: 12px; font-weight: 600; }.opportunity-item span { color: var(--bp-text-muted); font-size: 12px; line-height: 1.55; }.content-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 0; border-bottom: 1px solid #edf1f5; }.content-item:first-child { padding-top: 0; }.content-item:last-child { border-bottom: 0; padding-bottom: 0; }.content-item__main { display: flex; min-width: 0; flex-direction: column; gap: 4px; }.content-item__main strong, .content-item__main a { overflow: hidden; color: var(--bp-text-primary); font-size: 13px; font-weight: 600; text-decoration: none; text-overflow: ellipsis; white-space: nowrap; }.content-item__main a:hover { color: var(--bp-primary); }.content-item__main span { color: var(--bp-text-muted); font-size: 12px; }.content-item__likes { display: inline-flex; align-items: center; gap: 4px; flex: 0 0 auto; color: #b17b19; font-size: 12px; font-weight: 600; }.tasks-section { margin-top: 4px; }.section-heading { align-items: center; margin-bottom: 12px; }.task-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }.task-card :deep(.el-card__body) { display: flex; align-items: center; gap: 11px; padding: 15px; }.task-card > :deep(.el-card__body) > .el-icon { color: var(--bp-primary); font-size: 20px; }.task-card > :deep(.el-card__body) > div { flex: 1; min-width: 0; }.task-card strong { color: var(--bp-text-strong); font-size: 13px; }.task-card p { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 1199px) { .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.main-grid, .lower-grid { grid-template-columns: 1fr; }.opportunity-card { min-height: 0; } }
@media (max-width: 767px) { .focus-card__heading, .card-title-row, .section-heading { flex-direction: column; gap: 8px; }.focus-item { grid-template-columns: auto minmax(0, 1fr); }.focus-item > .el-button { grid-column: 2; justify-self: start; }.kpi-grid, .task-grid { grid-template-columns: 1fr; }.content-item { align-items: flex-start; }.task-card p { white-space: normal; } }
</style>
