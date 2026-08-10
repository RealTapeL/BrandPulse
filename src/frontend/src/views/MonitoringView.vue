<template>
  <div class="page monitoring-page">
    <div class="page-header">
      <h2>自动监控与告警</h2>
      <p class="desc">采集计划默认关闭；启用后仅对已登记项目执行真实浏览器采集，并保留任务和告警历史。</p>
    </div>

    <el-card shadow="never" class="section">
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

    <el-card shadow="never" class="section">
      <template #header><div class="section-title"><span>自动采集计划</span><span class="muted">按北京时间每天固定执行；空结果会失败并延迟重试。</span></div></template>
      <el-form :inline="true" :model="crawlForm" class="create-form">
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
        <el-table-column label="启用" width="100"><template #default="{ row }"><el-switch :model-value="row.enabled" @change="(value) => setCrawlEnabled(row, value)" /></template></el-table-column>
        <el-table-column prop="last_success_at" label="上次成功" width="180" />
        <el-table-column prop="last_error" label="最近错误" min-width="220" show-overflow-tooltip />
        <el-table-column label="操作" width="170" fixed="right"><template #default="{ row }"><el-button size="small" @click="runNow(row)">立即采集</el-button><el-button size="small" type="danger" link @click="removeCrawlSchedule(row)">删除</el-button></template></el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header><div class="section-title"><span>告警规则</span><el-button size="small" :loading="checkingAlerts" @click="checkNow">立即检查</el-button></div></template>
      <el-form :inline="true" :model="alertForm" class="create-form">
        <el-form-item label="规则名称"><el-input v-model="alertForm.name" placeholder="如：数据超过 72 小时未更新" /></el-form-item>
        <el-form-item label="监测范围"><el-select v-model="alertForm.scope_id" class="scope-select"><el-option label="全部范围" value="" /><el-option v-for="scope in scopes" :key="scope.scope_id" :label="scopeLabel(scope)" :value="scope.scope_id" /></el-select></el-form-item>
        <el-form-item label="指标"><el-select v-model="alertForm.metric" class="metric-select"><el-option label="数据新鲜度（小时）" value="data_freshness_hours" /><el-option label="热度" value="heat" /><el-option label="口碑" value="reputation" /><el-option label="SOV" value="sov" /><el-option label="评价数" value="review_count" /></el-select></el-form-item>
        <el-form-item label="条件"><el-select v-model="alertForm.operator" class="operator-select"><el-option v-for="item in operators" :key="item" :label="item" :value="item" /></el-select></el-form-item>
        <el-form-item label="阈值"><el-input-number v-model="alertForm.threshold" /></el-form-item>
        <el-form-item label="通知渠道"><el-select v-model="alertForm.destination_type" class="operator-select"><el-option label="不发送" value="" /><el-option label="邮件" value="email" /><el-option label="Webhook" value="webhook" /></el-select></el-form-item>
        <el-form-item v-if="alertForm.destination_type" label="地址"><el-input v-model="alertForm.destination_value" placeholder="邮箱或 https:// webhook" /></el-form-item>
        <el-form-item><el-button type="primary" :loading="creatingAlert" @click="addAlert">新增规则</el-button></el-form-item>
      </el-form>
      <div class="table-scroll">
        <el-table :data="alerts" border stripe empty-text="尚未配置告警规则">
        <el-table-column prop="name" label="规则" min-width="190" />
        <el-table-column label="监测范围" min-width="210"><template #default="{ row }">{{ scopeForBrandId(row.brand_id) }}</template></el-table-column>
        <el-table-column prop="metric" label="指标" width="160" />
        <el-table-column label="条件" width="120"><template #default="{ row }">{{ row.operator }} {{ row.threshold }}</template></el-table-column>
        <el-table-column label="启用" width="100"><template #default="{ row }"><el-switch :model-value="row.enabled" @change="(value) => setAlertEnabled(row, value)" /></template></el-table-column>
        <el-table-column label="操作" width="100"><template #default="{ row }"><el-button size="small" type="danger" link @click="removeAlert(row)">删除</el-button></template></el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header><div class="section-title"><span>告警检查历史</span><el-button size="small" @click="loadHistory">刷新</el-button></div></template>
      <div class="table-scroll">
        <el-table :data="history" border stripe empty-text="暂无告警检查记录">
        <el-table-column prop="checked_at" label="检查时间" width="180" />
        <el-table-column prop="alert_name" label="规则" min-width="180" />
        <el-table-column label="结果" width="100"><template #default="{ row }"><el-tag :type="row.triggered ? 'danger' : 'success'">{{ row.triggered ? '触发' : '正常' }}</el-tag></template></el-table-column>
        <el-table-column prop="metric_value" label="指标值" width="110" />
        <el-table-column prop="message" label="详情" min-width="320" show-overflow-tooltip />
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { checkAlertsNow, createAlert, deleteAlert, fetchAlertHistory, fetchAlerts, updateAlert } from '../api/alerts'
import { createCrawlSchedule, deleteCrawlSchedule, fetchCrawlSchedules, fetchMonitoringScopes, runCrawlScheduleNow, updateCrawlSchedule } from '../api/monitoring'

const scopes = ref([])
const crawlSchedules = ref([])
const alerts = ref([])
const history = ref([])
const loading = ref(false)
const creatingSchedule = ref(false)
const checkingAlerts = ref(false)
const creatingAlert = ref(false)
const operators = ['>', '>=', '<', '<=', '=']
const crawlForm = reactive({ scope_id: '', interval_minutes: 1440, run_hour: 9, run_minute: 0, timezone: 'Asia/Shanghai', max_attempts: 3, enabled: false })
const crawlTime = ref('09:00')
const alertForm = reactive({ name: '', scope_id: '', metric: 'data_freshness_hours', operator: '>', threshold: 72, destination_type: '', destination_value: '' })

function scopeLabel(scope) { return `${scope.city || '-'} · ${scope.mall_name || '-'} · ${scope.category || '-'}` }
function scopeForBrandId(brandId) { return scopes.value.find((item) => item.brand_id === brandId) ? scopeLabel(scopes.value.find((item) => item.brand_id === brandId)) : (brandId || '全部范围') }
function timeLabel(row) { return `${String(row.run_hour ?? 9).padStart(2, '0')}:${String(row.run_minute ?? 0).padStart(2, '0')}` }

async function load() {
  loading.value = true
  try {
    const [scopeResult, scheduleResult, alertRows] = await Promise.all([fetchMonitoringScopes(), fetchCrawlSchedules(), fetchAlerts()])
    scopes.value = scopeResult.items || []
    crawlSchedules.value = scheduleResult.items || []
    alerts.value = alertRows || []
    if (!crawlForm.scope_id && scopes.value.length) crawlForm.scope_id = scopes.value[0].scope_id
  } finally { loading.value = false }
}

async function loadHistory() { history.value = (await fetchAlertHistory()).items || [] }

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
    const scope = scopes.value.find((item) => item.scope_id === alertForm.scope_id)
    const destinations = alertForm.destination_type && alertForm.destination_value.trim()
      ? [{ type: alertForm.destination_type, value: alertForm.destination_value.trim() }]
      : []
    await createAlert({ name: alertForm.name || `${alertForm.metric} 阈值告警`, brand_id: scope?.brand_id || null, metric: alertForm.metric, operator: alertForm.operator, threshold: alertForm.threshold, destinations, enabled: true })
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
.muted { color: #909399; font-size: 12px; font-weight: 400; }

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
