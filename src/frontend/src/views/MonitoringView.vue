<template>
  <div :class="[{ page: !embedded }, 'monitoring-page', { 'embedded-view': embedded }]">
    <div v-if="!embedded" class="page-header">
      <h2>自动监控与告警</h2>
      <p class="desc">采集计划默认关闭；启用后仅对已登记项目执行真实浏览器采集，并保留任务和告警历史。</p>
    </div>

    <el-card v-if="show('collection')" shadow="never" class="section">
      <template #header><div class="section-title"><span>已登记监测范围</span><el-button size="small" :loading="loading" @click="load">刷新</el-button></div></template>
      <div class="table-scroll">
        <el-table :data="scopes" border stripe>
        <el-table-column label="项目 / 品类" min-width="250"><template #default="{ row }">{{ scopeLabel(row) }}</template></el-table-column>
        <el-table-column prop="brand_id" label="数据集 ID" min-width="160" show-overflow-tooltip />
        <el-table-column prop="latest_indicator_date" label="指标最新日期" width="140" />
        <el-table-column prop="latest_dianping_date" label="点评最新日期" width="140" />
        <el-table-column prop="latest_xiaohongshu_date" label="小红书最新日期" width="150" />
        </el-table>
      </div>
    </el-card>

    <el-card v-if="show('collection')" shadow="never" class="section">
      <template #header><div class="section-title"><span>自动采集计划</span><span class="muted">按北京时间每天固定执行；空结果会失败并延迟重试。</span></div></template>
      <el-form v-if="canMonitoring" :inline="true" :model="crawlForm" class="create-form">
        <el-form-item label="监测范围">
          <el-select v-model="crawlForm.scope_id" class="scope-select"><el-option v-for="scope in scopes" :key="scope.scope_id" :label="scopeLabel(scope)" :value="scope.scope_id" /></el-select>
        </el-form-item>
        <el-form-item label="执行时间"><el-time-select v-model="crawlTime" start="00:00" step="00:30" end="23:30" class="time-select" /></el-form-item>
        <el-form-item label="最大尝试"><el-input-number v-model="crawlForm.max_attempts" :min="1" :max="5" /></el-form-item>
        <el-form-item label="立即启用"><el-switch v-model="crawlForm.enabled" /></el-form-item>
        <el-form-item><el-button type="primary" :loading="creatingSchedule" :disabled="!crawlForm.scope_id" @click="addCrawlSchedule">新增计划</el-button></el-form-item>
      </el-form>
      <div class="table-scroll">
        <el-table :data="crawlSchedules" border stripe empty-text="尚未配置自动采集计划">
        <el-table-column label="项目 / 品类" min-width="230"><template #default="{ row }">{{ scopeLabel(row) }}</template></el-table-column>
        <el-table-column label="执行时间" width="125"><template #default="{ row }">{{ timeLabel(row) }}（上海）</template></el-table-column>
        <el-table-column prop="max_attempts" label="最大尝试" width="100" />
        <el-table-column label="启用" width="100"><template #default="{ row }"><el-switch :model-value="row.enabled" :disabled="!canMonitoring" @change="(value) => setCrawlEnabled(row, value)" /></template></el-table-column>
        <el-table-column prop="last_success_at" label="上次成功" width="180" />
        <el-table-column prop="last_error" label="最近错误" min-width="220" show-overflow-tooltip />
        <el-table-column v-if="canMonitoring" label="操作" width="170" fixed="right"><template #default="{ row }"><el-button size="small" @click="runNow(row)">立即采集</el-button><el-button size="small" type="danger" link @click="removeCrawlSchedule(row)">删除</el-button></template></el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card v-if="show('alerts')" shadow="never" class="section">
      <template #header><div class="section-title"><span>可信范围告警</span><el-button v-if="canAlerts" size="small" :loading="checkingAlerts" @click="checkNow">立即检查</el-button></div></template>
      <el-alert class="trust-note" type="info" :closable="false" show-icon title="新规则绑定一个城市 × 商场 × 品类范围，只读取该范围最新 ready/published 快照中的可信指标。未绑定范围的历史规则保留记录，但不会自动执行。" />
      <el-form v-if="canAlerts" :inline="true" :model="alertForm" class="create-form">
        <el-form-item label="规则名称"><el-input v-model="alertForm.name" placeholder="如：数据超过 72 小时未更新" /></el-form-item>
        <el-form-item label="监测范围"><el-select v-model="alertForm.scope_id" class="scope-select" placeholder="请选择范围"><el-option v-for="scope in scopes" :key="scope.scope_id" :label="scopeLabel(scope)" :value="scope.scope_id" /></el-select></el-form-item>
        <el-form-item label="指标"><el-select v-model="alertForm.metric" class="metric-select"><el-option label="数据新鲜度（小时）" value="data_freshness_hours" /><el-option label="点评累计评价数（公开存量）" value="dp_review_count_stock" /><el-option label="来源覆盖率" value="source_coverage_ratio" /><el-option label="实体映射覆盖率" value="entity_mapping_coverage" /></el-select></el-form-item>
        <el-form-item label="条件"><el-select v-model="alertForm.operator" class="operator-select"><el-option v-for="item in operators" :key="item" :label="item" :value="item" /></el-select></el-form-item>
        <el-form-item label="阈值"><el-input-number v-model="alertForm.threshold" /></el-form-item>
        <el-form-item label="持续提醒间隔"><el-input-number v-model="alertForm.cooldown_minutes" :min="5" :max="10080" :step="5" /><span class="form-suffix">分钟</span></el-form-item>
        <el-form-item label="恢复通知"><el-switch v-model="alertForm.notify_recovery" /></el-form-item>
        <el-form-item label="通知渠道"><el-select v-model="alertForm.destination_type" class="operator-select"><el-option label="不发送" value="" /><el-option label="邮件" value="email" /><el-option label="Webhook" value="webhook" /></el-select></el-form-item>
        <el-form-item v-if="alertForm.destination_type" label="地址"><el-input v-model="alertForm.destination_value" placeholder="邮箱或 https:// webhook" /></el-form-item>
        <el-form-item><el-button type="primary" :loading="creatingAlert" :disabled="!alertForm.scope_id" @click="addAlert">新增规则</el-button></el-form-item>
      </el-form>
      <div class="table-scroll">
        <el-table :data="alerts" border stripe empty-text="尚未配置告警规则">
        <el-table-column prop="name" label="规则" min-width="190" />
        <el-table-column label="监测范围" min-width="250"><template #default="{ row }"><span>{{ scopeForAlert(row) }}</span><el-tag v-if="row.rule_scope_status === 'legacy_unscoped'" class="legacy-tag" size="small" type="warning" effect="plain">历史未绑定</el-tag></template></el-table-column>
        <el-table-column label="指标" min-width="180"><template #default="{ row }">{{ metricLabel(row.metric) }}</template></el-table-column>
        <el-table-column label="条件" width="120"><template #default="{ row }">{{ row.operator }} {{ row.threshold }}</template></el-table-column>
        <el-table-column label="提醒策略" width="175"><template #default="{ row }">{{ row.cooldown_minutes }} 分钟 / 恢复{{ row.notify_recovery ? '通知' : '静默' }}</template></el-table-column>
        <el-table-column label="渠道" width="100"><template #default="{ row }">{{ destinationLabel(row.destinations) }}</template></el-table-column>
        <el-table-column label="启用" width="100"><template #default="{ row }"><el-switch :model-value="row.enabled" :disabled="!canAlerts" @change="(value) => setAlertEnabled(row, value)" /></template></el-table-column>
        <el-table-column v-if="canAlerts" label="操作" width="100"><template #default="{ row }"><el-button size="small" type="danger" link @click="removeAlert(row)">删除</el-button></template></el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card v-if="show('runs')" shadow="never" class="section">
      <template #header><div class="section-title"><span>告警检查历史</span><el-button size="small" @click="loadHistory">刷新</el-button></div></template>
      <div class="table-scroll">
        <el-table :data="history" border stripe empty-text="暂无告警检查记录">
        <el-table-column prop="checked_at" label="检查时间" width="180" />
        <el-table-column prop="alert_name" label="规则" min-width="180" />
        <el-table-column label="事件" width="110"><template #default="{ row }"><el-tag :type="eventType(row.event_type)">{{ eventLabel(row.event_type, row.triggered) }}</el-tag></template></el-table-column>
        <el-table-column label="通知" width="105"><template #default="{ row }"><el-tag :type="notificationType(row.notification_status)" effect="plain">{{ notificationLabel(row.notification_status) }}</el-tag></template></el-table-column>
        <el-table-column prop="metric_value" label="指标值" width="110" />
        <el-table-column prop="message" label="详情" min-width="320" show-overflow-tooltip />
        </el-table>
      </div>
    </el-card>

    <el-card v-if="show('notifications')" shadow="never" class="section">
      <template #header><div class="section-title"><span>通知投递记录</span><span class="muted">每个邮箱或 Webhook 独立记录发送结果，失败自动退避重试。</span></div></template>
      <div class="table-scroll">
        <el-table :data="deliveries" border stripe empty-text="暂无通知投递记录">
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column prop="alert_name" label="规则" min-width="180" />
        <el-table-column label="事件" width="100"><template #default="{ row }">{{ eventLabel(row.event_type) }}</template></el-table-column>
        <el-table-column label="目标" min-width="220" show-overflow-tooltip><template #default="{ row }">{{ row.destination_type }} · {{ row.destination_value }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="deliveryType(row.status)">{{ deliveryLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="attempt_count" label="尝试次数" width="100" />
        <el-table-column prop="last_error" label="最近错误" min-width="220" show-overflow-tooltip />
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { checkAlertsNow, createAlert, deleteAlert, fetchAlertDeliveries, fetchAlertHistory, fetchAlerts, updateAlert } from '../api/alerts'
import { createCrawlSchedule, deleteCrawlSchedule, fetchCrawlSchedules, fetchMonitoringScopes, runCrawlScheduleNow, updateCrawlSchedule } from '../api/monitoring'
import { usePermissions } from '../composables/usePermissions'

const props = defineProps({ embedded: { type: Boolean, default: false }, activeSection: { type: String, default: 'all' } })
const { can } = usePermissions()
const canMonitoring = can('monitoring.manage')
const canAlerts = can('alert.manage')

const scopes = ref([])
const crawlSchedules = ref([])
const alerts = ref([])
const history = ref([])
const deliveries = ref([])
const loading = ref(false)
const creatingSchedule = ref(false)
const checkingAlerts = ref(false)
const creatingAlert = ref(false)
const operators = ['>', '>=', '<', '<=', '=']
const crawlForm = reactive({ scope_id: '', interval_minutes: 1440, run_hour: 9, run_minute: 0, timezone: 'Asia/Shanghai', max_attempts: 3, enabled: false })
const crawlTime = ref('09:00')
const alertForm = reactive({ name: '', scope_id: '', metric: 'data_freshness_hours', operator: '>', threshold: 72, cooldown_minutes: 60, notify_recovery: true, destination_type: '', destination_value: '' })

function scopeLabel(scope) { return `${scope.city || '-'} · ${scope.mall_name || '-'} · ${scope.category || '-'}` }
function scopeForAlert(row) {
  if (row.rule_scope_status === 'trusted_scope') {
    const scope = scopes.value.find((item) => item.scope_id === row.scope_id)
    return scope ? scopeLabel(scope) : `范围 ${row.scope_id}`
  }
  return '历史规则（未绑定可信范围，已停止自动检查）'
}
function metricLabel(metric) {
  return {
    data_freshness_hours: '数据新鲜度（小时）',
    dp_review_count_stock: '点评累计评价数（公开存量）',
    source_coverage_ratio: '来源覆盖率',
    entity_mapping_coverage: '实体映射覆盖率',
  }[metric] || `历史指标：${metric}`
}
function timeLabel(row) { return `${String(row.run_hour ?? 9).padStart(2, '0')}:${String(row.run_minute ?? 0).padStart(2, '0')}` }
function destinationLabel(items) { return (items || []).map((item) => item.type === 'email' ? '邮件' : 'Webhook').join('、') || '不发送' }
function eventLabel(event, triggered = false) { return { trigger: '首次触发', reminder: '持续提醒', recovery: '恢复', check: triggered ? '异常检查' : '正常检查' }[event] || event }
function eventType(event) { return { trigger: 'danger', reminder: 'warning', recovery: 'success', check: 'info' }[event] || 'info' }
function notificationLabel(status) { return { queued: '待发送', sent: '已发送', retrying: '重试中', failed: '失败', partial: '部分成功', suppressed: '已抑制', not_requested: '无需发送' }[status] || status }
function notificationType(status) { return { sent: 'success', failed: 'danger', retrying: 'warning', partial: 'warning', queued: 'info', suppressed: 'info', not_requested: 'info' }[status] || 'info' }
function deliveryLabel(status) { return { pending: '待发送', sending: '发送中', retry: '待重试', sent: '已发送', failed: '失败', cancelled: '已取消' }[status] || status }
function deliveryType(status) { return { sent: 'success', failed: 'danger', retry: 'warning', sending: 'warning', pending: 'info', cancelled: 'info' }[status] || 'info' }
function show(section) { return props.activeSection === 'all' || props.activeSection === section }

async function load() {
  loading.value = true
  try {
    const needCollection = show('collection')
    const needAlerts = show('alerts')
    const [scopeResult, scheduleResult, alertRows] = await Promise.all([
      needCollection || needAlerts ? fetchMonitoringScopes() : Promise.resolve(null),
      needCollection ? fetchCrawlSchedules() : Promise.resolve(null),
      needAlerts ? fetchAlerts() : Promise.resolve(null),
    ])
    if (scopeResult) scopes.value = scopeResult.items || []
    if (scheduleResult) crawlSchedules.value = scheduleResult.items || []
    if (alertRows) alerts.value = alertRows || []
    if (!crawlForm.scope_id && scopes.value.length) crawlForm.scope_id = scopes.value[0].scope_id
    if (!alertForm.scope_id && scopes.value.length) alertForm.scope_id = scopes.value[0].scope_id
  } finally { loading.value = false }
}

async function loadHistory() {
  if (show('runs')) { history.value = (await fetchAlertHistory()).items || [] }
  if (show('notifications')) { deliveries.value = (await fetchAlertDeliveries()).items || [] }
}

async function addCrawlSchedule() {
  creatingSchedule.value = true
  try {
    const [run_hour, run_minute] = crawlTime.value.split(':').map(Number)
    await createCrawlSchedule({ ...crawlForm, run_hour, run_minute })
    ElMessage.success('每日自动采集计划已保存')
    await load()
  } finally { creatingSchedule.value = false }
}
async function setCrawlEnabled(row, enabled) { await updateCrawlSchedule(row.schedule_id, { enabled }); ElMessage.success(enabled ? '自动采集已启用' : '自动采集已暂停'); await load() }
async function runNow(row) { await runCrawlScheduleNow(row.schedule_id); ElMessage.success('真实采集任务已进入后台队列') }
async function removeCrawlSchedule(row) { await deleteCrawlSchedule(row.schedule_id); ElMessage.success('自动采集计划已删除'); await load() }

async function addAlert() {
  creatingAlert.value = true
  try {
    if (!alertForm.scope_id) {
      ElMessage.warning('请先选择一个可信监测范围')
      return
    }
    const destinations = alertForm.destination_type && alertForm.destination_value.trim()
      ? [{ type: alertForm.destination_type, value: alertForm.destination_value.trim() }]
      : []
    await createAlert({ name: alertForm.name || `${metricLabel(alertForm.metric)}阈值告警`, scope_id: alertForm.scope_id, metric: alertForm.metric, operator: alertForm.operator, threshold: alertForm.threshold, cooldown_minutes: alertForm.cooldown_minutes, notify_recovery: alertForm.notify_recovery, destinations, enabled: true })
    ElMessage.success('告警规则已保存'); alertForm.name = ''; alertForm.destination_value = ''; await load()
  } finally { creatingAlert.value = false }
}
async function setAlertEnabled(row, enabled) { await updateAlert(row.id, { enabled }); ElMessage.success(enabled ? '告警已启用' : '告警已暂停'); await load() }
async function removeAlert(row) { await deleteAlert(row.id); ElMessage.success('告警规则已删除'); await load(); await loadHistory() }
async function checkNow() { checkingAlerts.value = true; try { const result = await checkAlertsNow(); ElMessage.success(`检查完成，触发 ${result.triggered} 条`); await loadHistory() } finally { checkingAlerts.value = false } }

onMounted(async () => { await Promise.all([load(), loadHistory()]) })
</script>

<style scoped>
.section { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-weight: 600; }
.create-form { display: flex; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.scope-select { width: min(250px, 100%); }
.time-select { width: 110px; }
.metric-select { width: 155px; }
.operator-select { width: 76px; }
.form-suffix { margin-left: 6px; color: #606266; }
.muted { color: #909399; font-size: 12px; font-weight: 400; }
.trust-note { margin-bottom: 12px; }
.legacy-tag { margin-left: 8px; vertical-align: middle; }

@media (max-width: 767px) {
  .section-title {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .scope-select,
  .time-select,
  .metric-select,
  .operator-select {
    width: 100%;
  }
}
</style>
