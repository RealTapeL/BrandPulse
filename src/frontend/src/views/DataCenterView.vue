<template>
  <div class="page data-center-page">
    <PageHeader title="数据中心" :description="scopeStore.current ? `${scopeStore.label} 的来源状态、原始数据与质量处理。` : '查看已接入数据的来源状态、原始记录与质量问题。'">
      <template #actions><el-button :loading="loading" @click="loadOverview"><el-icon><Refresh /></el-icon>刷新概览</el-button></template>
    </PageHeader>
    <el-alert v-if="error" class="data-error" type="error" :closable="false" show-icon :title="error"><template #default><el-button size="small" @click="loadOverview">重试</el-button></template></el-alert>
    <el-tabs v-model="activeTab" class="data-tabs">
      <el-tab-pane label="数据概览" name="overview"><template v-if="activeTab === 'overview'"><div v-if="loading" class="source-grid"><el-skeleton v-for="n in 4" :key="n" :rows="3" animated /></div><template v-else><div class="source-grid"><el-card v-for="source in sources" :key="source.key" shadow="never" class="source-card"><div class="source-card__head"><div><el-icon><component :is="source.icon" /></el-icon><h2>{{ source.name }}</h2></div><DataFreshnessBadge :value="source.updatedAt" :source="source.source" /></div><div class="source-card__value">{{ source.count }}</div><p>{{ source.description }}</p><div class="source-card__foot"><span>{{ source.status }}</span><el-button link type="primary" @click="openSource(source.tab)">查看数据</el-button></div></el-card></div><el-card shadow="never" class="overview-note"><div><h2>数据质量与可追溯性</h2><p>开放问题 {{ openIssueCount }} 个，待匹配门店 {{ pendingStoreCount }} 个；这些问题可能影响品牌判断与汇总口径。</p></div><el-button type="primary" plain @click="activeTab = 'quality'">处理数据问题</el-button></el-card></template></template></el-tab-pane>
      <el-tab-pane label="原始数据浏览" name="tables"><TablesView v-if="activeTab === 'tables'" embedded /></el-tab-pane>
      <el-tab-pane label="快照与来源" name="snapshots"><SnapshotRegistryPanel v-if="activeTab === 'snapshots'" :scope-id="scopeStore.currentId" /></el-tab-pane>
      <el-tab-pane label="数据质量" name="quality"><DataGovernanceView v-if="activeTab === 'quality'" embedded initial-tab="issues" /></el-tab-pane>
      <el-tab-pane label="原始记录映射" name="matching"><DataGovernanceView v-if="activeTab === 'matching'" embedded initial-tab="observations" /></el-tab-pane>
      <el-tab-pane label="数据血缘" name="lineage"><DataGovernanceView v-if="activeTab === 'lineage'" embedded initial-tab="lineage" /></el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import DataFreshnessBadge from '../components/DataFreshnessBadge.vue'
import TablesView from './TablesView.vue'
import DataGovernanceView from './DataGovernanceView.vue'
import SnapshotRegistryPanel from '../components/SnapshotRegistryPanel.vue'
import { fetchDashboard } from '../api/dashboard'
import { fetchGovernanceSummary } from '../api/dataGovernance'
import { fetchTableData } from '../api/tables'
import { fetchOperationsReadiness } from '../api/operations'
import { useScopeStore } from '../stores/scope'

const route = useRoute(); const router = useRouter(); const scopeStore = useScopeStore(); const dashboard = ref(null); const governance = ref(null); const operationsTotal = ref(null); const operationsReady = ref(null); const loading = ref(false); const error = ref('')
const allowedTabs = ['overview', 'tables', 'snapshots', 'quality', 'matching', 'lineage']
const activeTab = computed({ get: () => allowedTabs.includes(route.query.tab) ? route.query.tab : 'overview', set: (tab) => router.replace({ path: '/data', query: { tab } }) })
const xhsLatest = computed(() => (dashboard.value?.xhs_notes || []).reduce((latest, note) => (note.crawl_date || '') > latest ? note.crawl_date : latest, ''))
const openIssueCount = computed(() => Number(governance.value?.records?.open_issues || 0))
const pendingStoreCount = computed(() => Number(governance.value?.records?.pending_observation_mappings || 0))
const sources = computed(() => [
  { key: 'dianping', icon: 'Shop', name: '大众点评', source: '点评', count: `${dashboard.value?.dp_shops?.length || 0} 条`, updatedAt: dashboard.value?.crawl_date, status: dashboard.value?.dp_shops?.length ? '当前范围最新门店快照' : '暂无门店记录', description: '门店评分、评价数、人均与位置等公开采集数据。', tab: 'snapshots' },
  { key: 'xiaohongshu', icon: 'Document', name: '小红书', source: '小红书', count: `${dashboard.value?.xhs_notes?.length || 0} 条`, updatedAt: xhsLatest.value, status: dashboard.value?.xhs_notes?.length ? '当前范围已采集笔记' : '暂无内容记录', description: '已采集的标题、作者、点赞与发布时间等公开内容数据。', tab: 'snapshots' },
  { key: 'indicators', icon: 'DataAnalysis', name: '快照指标', source: '指标', count: `${dashboard.value?.metric_summary?.length || 0} 条`, updatedAt: dashboard.value?.stat_date, status: dashboard.value?.metric_summary?.length ? '已绑定可信快照' : '指标尚未就绪', description: '公开评价存量、贝叶斯口碑、单来源评价份额与数据质量指标；不会将其包装为经营表现。', tab: 'tables' },
  { key: 'operations', icon: 'Money', name: '内部 POS / 经营数据', source: '经营', count: operationsTotal.value === null ? '未读取' : `${operationsTotal.value} 条`, updatedAt: operationsReady.value?.latest_record_date || '', status: operationsReady.value?.ready_for_sales_metric ? '已完成映射，可用于经营分析' : '尚未接入或映射未完成', description: '只接受授权导入的销售、成本、合同等内部经营记录。', tab: 'tables' },
])
function openSource(tab) { activeTab.value = tab }
async function loadOverview() { loading.value = true; error.value = ''; try { await scopeStore.load(); if (!scopeStore.currentId) { dashboard.value = null; return }; const [data, summary, operations, readiness] = await Promise.all([fetchDashboard(scopeStore.currentId), fetchGovernanceSummary().catch(() => null), fetchTableData('store_operations', { page: 1, size: 1 }).catch(() => ({ total: null })), fetchOperationsReadiness(scopeStore.currentId).catch(() => null)]); dashboard.value = data; governance.value = summary; operationsTotal.value = operations.total; operationsReady.value = readiness } catch (err) { error.value = `数据概览加载失败：${err?.response?.data?.detail || err?.message || err}` } finally { loading.value = false } }
watch(() => scopeStore.currentId, () => { if (activeTab.value === 'overview' && !loading.value) loadOverview() }); onMounted(loadOverview)
</script>

<style scoped>
.data-error { margin-bottom: 16px; }.source-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }.source-card__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }.source-card__head > div { display: flex; align-items: center; gap: 7px; }.source-card__head .el-icon { color: var(--bp-primary); font-size: 18px; }.source-card h2, .overview-note h2 { margin: 0; color: var(--bp-text-strong); font-size: 15px; }.source-card__value { margin: 19px 0 6px; color: var(--bp-text-strong); font-size: 27px; font-weight: 700; }.source-card p, .overview-note p { min-height: 39px; margin: 0; color: var(--bp-text-muted); font-size: 12px; line-height: 1.6; }.source-card__foot { display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-top: 15px; padding-top: 10px; border-top: 1px solid #eef2f6; color: var(--bp-text-secondary); font-size: 12px; }.overview-note { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-top: 16px; }.overview-note p { min-height: 0; margin-top: 5px; }.data-tabs :deep(.el-tabs__header) { margin-bottom: 18px; }.data-tabs :deep(.el-tabs__item) { height: 38px; font-weight: 500; } @media (max-width: 1199px) { .source-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } } @media (max-width: 767px) { .source-grid { grid-template-columns: 1fr; }.overview-note { align-items: flex-start; flex-direction: column; gap: 12px; } }
</style>
