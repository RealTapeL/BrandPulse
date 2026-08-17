<template>
  <div class="page automation-page">
    <PageHeader title="自动化中心" description="统一管理真实采集、告警、报告、运行记录与通知投递。所有计划均需在服务端启用后才会执行。"><template #actions><el-button :loading="loading" @click="load"><el-icon><Refresh /></el-icon>刷新状态</el-button></template></PageHeader>
    <div class="automation-summary"><el-card shadow="never"><span>启用采集计划</span><strong>{{ enabledSchedules }}</strong><small>按已登记范围执行</small></el-card><el-card shadow="never"><span>启用告警规则</span><strong>{{ enabledAlerts }}</strong><small>指标异常与新鲜度检查</small></el-card><el-card shadow="never"><span>报告计划</span><strong>{{ enabledReports }}</strong><small>需通过数据新鲜度校验</small></el-card><el-card shadow="never"><span>待处理事项</span><strong>{{ openCases }}</strong><small>已由告警、数据问题或人工创建</small></el-card></div>
    <el-tabs v-model="activeTab" class="automation-tabs"><el-tab-pane label="采集计划" name="collection"><MonitoringView v-if="activeTab === 'collection'" embedded active-section="collection" /></el-tab-pane><el-tab-pane label="告警规则" name="alerts"><MonitoringView v-if="activeTab === 'alerts'" embedded active-section="alerts" /></el-tab-pane><el-tab-pane label="定时报告" name="reports"><ReportsView v-if="activeTab === 'reports'" embedded /></el-tab-pane><el-tab-pane label="事项闭环" name="cases"><BusinessCasesPanel v-if="activeTab === 'cases'" /></el-tab-pane><el-tab-pane label="运行记录" name="runs"><div v-if="activeTab === 'runs'" class="runs-stack"><MonitoringView embedded active-section="runs" /><TaskRunPanel /></div></el-tab-pane><el-tab-pane label="通知记录" name="notifications"><div v-if="activeTab === 'notifications'" class="notification-stack"><MonitoringView embedded active-section="notifications" /><ReportDeliveryLogPanel /></div></el-tab-pane></el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import MonitoringView from './MonitoringView.vue'
import ReportsView from './ReportsView.vue'
import TaskRunPanel from '../components/TaskRunPanel.vue'
import BusinessCasesPanel from '../components/BusinessCasesPanel.vue'
import ReportDeliveryLogPanel from '../components/ReportDeliveryLogPanel.vue'
import { fetchAlerts } from '../api/alerts'
import { fetchCrawlSchedules } from '../api/monitoring'
import { fetchReportSchedules } from '../api/reports'
import { fetchCases } from '../api/cases'

const route = useRoute(); const router = useRouter(); const loading = ref(false); const schedules = ref([]); const alerts = ref([]); const reports = ref([]); const cases = ref([]); const tabs = ['collection', 'alerts', 'reports', 'cases', 'runs', 'notifications']
const activeTab = computed({ get: () => tabs.includes(route.query.tab) ? route.query.tab : 'collection', set: (tab) => router.replace({ path: '/automation', query: { tab } }) })
const enabledSchedules = computed(() => schedules.value.filter((item) => item.enabled).length); const enabledAlerts = computed(() => alerts.value.filter((item) => item.enabled).length); const enabledReports = computed(() => reports.value.filter((item) => item.enabled).length); const openCases = computed(() => cases.value.filter((item) => !['resolved', 'closed'].includes(item.status)).length)
async function load() { loading.value = true; try { const [crawl, alertRules, reportRows, caseRows] = await Promise.all([fetchCrawlSchedules(), fetchAlerts(), fetchReportSchedules(), fetchCases().catch(() => ({ items: [] }))]); schedules.value = crawl.items || []; alerts.value = Array.isArray(alertRules) ? alertRules : []; reports.value = reportRows.items || []; cases.value = caseRows.items || [] } finally { loading.value = false } }
onMounted(load)
</script>

<style scoped>
.automation-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }.automation-summary :deep(.el-card__body) { display: flex; flex-direction: column; padding: 15px 17px; }.automation-summary span, .automation-summary small { color: var(--bp-text-muted); font-size: 12px; }.automation-summary strong { margin: 8px 0 5px; color: var(--bp-text-strong); font-size: 26px; line-height: 1; }.automation-tabs :deep(.el-tabs__header) { margin-bottom: 18px; } @media (max-width: 1199px) { .automation-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } } @media (max-width: 767px) { .automation-summary { grid-template-columns: 1fr; } }
</style>
