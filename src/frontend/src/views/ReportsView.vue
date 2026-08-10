<template>
  <div class="page reports-page">
    <div class="page-header">
      <div>
        <h2>自动报告与导出</h2>
        <p class="desc">报告仅使用通过新鲜度校验的真实指标和来源快照；数据过期时会明确拒绝生成。</p>
      </div>
    </div>

    <el-card shadow="never" class="section">
      <template #header>
        <div class="section-title"><span>报告数据状态</span><el-button size="small" :loading="loading" @click="load">刷新</el-button></div>
      </template>
      <div class="toolbar">
        <el-select v-model="scopeId" class="scope-select" @change="onScopeChange">
          <el-option v-for="scope in scopes" :key="scope.scope_id" :label="scopeLabel(scope)" :value="scope.scope_id" />
        </el-select>
        <el-button type="primary" :disabled="!readiness?.ready" :loading="creating" @click="generate('xlsx')">生成 XLSX 报告</el-button>
        <el-button :disabled="!readiness?.ready" :loading="creating" @click="generate('csv')">导出 CSV 快照</el-button>
      </div>
      <el-alert v-if="readiness" :type="readiness.ready ? 'success' : 'warning'" :closable="false" show-icon :title="readiness.ready ? `数据可用：指标 ${readiness.stat_date}，来源 ${readiness.crawl_date}` : readiness.reasons.join('；')" />
    </el-card>

    <el-card shadow="never" class="section">
      <template #header>
        <div class="section-title"><span>报告生成记录</span><span class="muted">生成中会自动刷新</span></div>
      </template>
      <div class="table-scroll">
        <el-table :data="reports" border stripe empty-text="暂无报告记录">
          <el-table-column prop="created_at" label="创建时间" width="180" />
          <el-table-column label="范围" min-width="220"><template #default="{ row }">{{ scopeLabel(row) }}</template></el-table-column>
          <el-table-column prop="file_format" label="格式" width="90" />
          <el-table-column prop="status" label="状态" width="100"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column prop="snapshot_date" label="快照日期" width="120" />
          <el-table-column prop="row_count" label="记录数" width="90" />
          <el-table-column prop="error" label="错误" min-width="220" show-overflow-tooltip />
          <el-table-column label="操作" width="110"><template #default="{ row }"><el-button v-if="row.status === 'success'" size="small" type="success" @click="download(row)">下载</el-button></template></el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header>
        <div class="section-title"><span>定时报告计划</span><span class="muted">默认关闭；日报/周报到点后先经过相同的数据新鲜度校验。</span></div>
      </template>
      <el-form :inline="true" :model="scheduleForm" class="toolbar">
        <el-form-item label="范围"><el-select v-model="scheduleForm.scope_id" class="scope-select"><el-option v-for="scope in scopes" :key="scope.scope_id" :label="scopeLabel(scope)" :value="scope.scope_id" /></el-select></el-form-item>
        <el-form-item label="频率"><el-select v-model="scheduleForm.frequency" class="short-select"><el-option label="日报" value="daily" /><el-option label="周报" value="weekly" /></el-select></el-form-item>
        <el-form-item v-if="scheduleForm.frequency === 'weekly'" label="星期"><el-select v-model="scheduleForm.weekday" class="short-select"><el-option v-for="day in weekdays" :key="day.value" :label="day.label" :value="day.value" /></el-select></el-form-item>
        <el-form-item label="时间"><el-time-select v-model="scheduleTime" start="00:00" step="00:30" end="23:30" class="time-select" /></el-form-item>
        <el-form-item label="格式"><el-select v-model="scheduleForm.file_format" class="short-select"><el-option label="XLSX" value="xlsx" /><el-option label="CSV" value="csv" /></el-select></el-form-item>
        <el-form-item label="启用"><el-switch v-model="scheduleForm.enabled" /></el-form-item>
        <el-form-item><el-button type="primary" :disabled="!scheduleForm.scope_id" @click="addSchedule">保存计划</el-button></el-form-item>
      </el-form>
      <div class="table-scroll">
        <el-table :data="schedules" border stripe empty-text="暂无定时报告计划">
          <el-table-column label="范围" min-width="220"><template #default="{ row }">{{ scopeLabel(row) }}</template></el-table-column>
          <el-table-column prop="frequency" label="频率" width="90" />
          <el-table-column label="时间" width="110"><template #default="{ row }">{{ timeLabel(row) }}</template></el-table-column>
          <el-table-column prop="file_format" label="格式" width="90" />
          <el-table-column label="启用" width="100"><template #default="{ row }"><el-switch :model-value="row.enabled" @change="(value) => setScheduleEnabled(row, value)" /></template></el-table-column>
          <el-table-column prop="last_enqueued_for" label="最近生成日" width="130" />
          <el-table-column prop="last_error" label="最近错误" min-width="220" show-overflow-tooltip />
          <el-table-column label="操作" width="90"><template #default="{ row }"><el-button size="small" type="danger" link @click="removeSchedule(row)">删除</el-button></template></el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchMonitoringScopes } from '../api/monitoring'
import { createReport, createReportSchedule, deleteReportSchedule, downloadReport, fetchReportReadiness, fetchReports, fetchReportSchedules, updateReportSchedule } from '../api/reports'

const scopes = ref([]); const scopeId = ref(''); const readiness = ref(null); const reports = ref([]); const schedules = ref([])
const loading = ref(false); const creating = ref(false); let pollTimer = null; let polling = false
const scheduleForm = reactive({ scope_id: '', frequency: 'daily', weekday: 0, file_format: 'xlsx', enabled: false })
const scheduleTime = ref('09:00')
const weekdays = [{ value: 0, label: '周一' }, { value: 1, label: '周二' }, { value: 2, label: '周三' }, { value: 3, label: '周四' }, { value: 4, label: '周五' }, { value: 5, label: '周六' }, { value: 6, label: '周日' }]
function scopeLabel(scope) { return `${scope.city || '-'} · ${scope.mall_name || '-'} · ${scope.category || '-'}` }
function statusType(status) { return { success: 'success', failed: 'danger', skipped: 'warning', running: 'warning', pending: 'info' }[status] || 'info' }
function statusLabel(status) { return { success: '完成', failed: '失败', skipped: '跳过', running: '生成中', pending: '排队中' }[status] || status }
function timeLabel(row) { return `${String(row.hour).padStart(2, '0')}:${String(row.minute).padStart(2, '0')}${row.frequency === 'weekly' ? ` · ${weekdays.find((item) => item.value === row.weekday)?.label || ''}` : ''}` }

async function loadReadiness() { if (scopeId.value) readiness.value = await fetchReportReadiness(scopeId.value); else readiness.value = null }
async function loadReports() { reports.value = (await fetchReports(scopeId.value)).items || []; startPolling() }
async function onScopeChange() { await Promise.all([loadReadiness(), loadReports()]) }
async function load() { loading.value = true; try { const scopeResult = await fetchMonitoringScopes(); scopes.value = scopeResult.items || []; if (!scopeId.value && scopes.value.length) scopeId.value = scopes.value.find((item) => item.latest_indicator_date)?.scope_id || scopes.value[0].scope_id; scheduleForm.scope_id ||= scopeId.value; const [scheduleResult] = await Promise.all([fetchReportSchedules(), onScopeChange()]); schedules.value = scheduleResult.items || [] } finally { loading.value = false } }
async function generate(fileFormat) { creating.value = true; try { await createReport({ scope_id: scopeId.value, file_format: fileFormat }); ElMessage.success('报告任务已进入后台队列'); await load() } finally { creating.value = false } }
async function download(row) { await downloadReport(row.report_id); ElMessage.success('报告下载已开始') }
async function addSchedule() { const [hour, minute] = scheduleTime.value.split(':').map(Number); const payload = { ...scheduleForm, hour, minute, weekday: scheduleForm.frequency === 'weekly' ? scheduleForm.weekday : null }; await createReportSchedule(payload); ElMessage.success('定时报告计划已保存'); await load() }
async function setScheduleEnabled(row, enabled) { await updateReportSchedule(row.schedule_id, { enabled }); ElMessage.success(enabled ? '定时报告已启用' : '定时报告已暂停'); await load() }
async function removeSchedule(row) { await deleteReportSchedule(row.schedule_id); ElMessage.success('定时报告计划已删除'); await load() }
function startPolling() {
  if (pollTimer || !reports.value.some((item) => ['pending', 'running'].includes(item.status))) return
  pollTimer = window.setInterval(async () => {
    if (polling) return
    polling = true
    try {
      const result = await fetchReports(scopeId.value)
      reports.value = result.items || []
      if (!reports.value.some((item) => ['pending', 'running'].includes(item.status))) {
        window.clearInterval(pollTimer)
        pollTimer = null
      }
    } catch {
      // 请求拦截器负责展示错误；保留定时器，下一轮继续获取后台状态。
    } finally {
      polling = false
    }
  }, 3000)
}
onMounted(load); onBeforeUnmount(() => { if (pollTimer) window.clearInterval(pollTimer) })
</script>

<style scoped>
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-weight: 600; flex-wrap: wrap; }
.scope-select { width: min(260px, 100%); }
.short-select { width: 100px; }
.time-select { width: 110px; }
.muted { color: #909399; font-size: 12px; font-weight: 400; }

@media (max-width: 767px) {
  .scope-select,
  .short-select,
  .time-select {
    width: 100%;
  }
}
</style>
