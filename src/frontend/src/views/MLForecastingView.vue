<template>
  <div class="page ml-page">
    <div class="page-header">
      <h2>机器学习预测</h2>
      <p class="desc">数据输入、后台训练、预测导出和全过程日志都在此闭环管理。</p>
    </div>

    <el-alert
      title="公开基准数据和用户上传数据默认仅用于模型验证，上传内容与 store_operations 内部经营表隔离。"
      type="warning"
      :closable="false"
      show-icon
      class="notice"
    />

    <el-card shadow="never" class="section">
      <template #header>
        <div class="section-title">
          <span>输入真实数据</span>
          <span class="muted">支持 CSV、XLSX、XLSM；上传后会先校验字段、日期和缺失值</span>
        </div>
      </template>
      <div class="upload-row">
        <el-upload
          action="#"
          :auto-upload="true"
          :show-file-list="false"
          accept=".csv,.xlsx,.xlsm"
          :before-upload="handleUpload"
        >
          <el-button type="primary" :loading="uploading">选择并校验数据文件</el-button>
        </el-upload>
        <span class="muted">必需列：date、store、item、sales；也支持常见中文列名。</span>
      </div>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header>
        <div class="section-title">
          <span>已登记数据集</span>
          <el-button size="small" :loading="loadingDatasets" @click="loadDatasets">刷新</el-button>
        </div>
      </template>
      <div class="table-scroll">
        <el-table v-loading="loadingDatasets" :data="datasets" border stripe>
        <el-table-column prop="name" label="数据集" min-width="230" />
        <el-table-column prop="description" label="说明" min-width="320" show-overflow-tooltip />
        <el-table-column label="来源" width="145">
          <template #default="{ row }">
            <el-tag :type="row.data_origin === 'user_upload' ? 'success' : 'warning'">
              {{ row.data_origin === 'user_upload' ? '用户上传' : '公开基准' }}
            </el-tag>
            <div class="muted">{{ row.production_eligible ? '可用于生产' : '仅验证' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="校验状态" width="150">
          <template #default="{ row }">
            <template v-if="row.data_origin === 'user_upload'">
              <el-tag :type="datasetStatusType(row.status)">{{ datasetStatusLabel(row.status) }}</el-tag>
              <div v-if="row.validation?.rows" class="muted">{{ row.validation.rows }} 行</div>
            </template>
            <template v-else>
              <el-tag :type="row.downloaded ? 'success' : 'info'">
                {{ row.downloaded ? `${row.validation?.rows || 0} 行已下载` : '可下载' }}
              </el-tag>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="时间范围" width="210">
          <template #default="{ row }">
            {{ row.validation?.min_date || '-' }} 至 {{ row.validation?.max_date || '-' }}
          </template>
        </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header>
        <div class="section-title">
          <span>启动训练</span>
          <span class="muted">训练、回测和模型落盘由 brandpulse-ml 后台队列执行</span>
        </div>
      </template>
      <el-form :inline="true" :model="form">
        <el-form-item label="数据集">
          <el-select v-model="form.datasetKey" class="dataset-select">
            <el-option
              v-for="dataset in trainableDatasets"
              :key="dataset.key"
              :label="dataset.name"
              :value="dataset.key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="回测天数">
          <el-input-number v-model="form.validationDays" :min="7" :max="180" />
        </el-form-item>
        <el-form-item label="预测天数">
          <el-input-number v-model="form.horizon" :min="1" :max="90" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="starting" :disabled="!trainableDatasets.length" @click="startTraining">
            开始训练并回测
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header>
        <div class="section-title">
          <span>训练运行</span>
          <el-button size="small" :loading="loadingRuns" @click="loadRuns">刷新</el-button>
        </div>
      </template>
      <div class="table-scroll">
        <el-table v-loading="loadingRuns" :data="runs" border stripe>
        <el-table-column prop="created_at" label="创建时间" width="190" />
        <el-table-column prop="dataset_key" label="数据集" width="170" show-overflow-tooltip />
        <el-table-column label="状态" width="105">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="回测指标" min-width="285">
          <template #default="{ row }">
            <template v-if="row.metrics && Object.keys(row.metrics).length">
              MAE {{ formatMetric(row.metrics.mae) }} · RMSE {{ formatMetric(row.metrics.rmse) }} ·
              WAPE {{ formatPercent(row.metrics.wape) }}
            </template>
            <span v-else class="muted">训练完成后显示</span>
          </template>
        </el-table-column>
        <el-table-column prop="model_id" label="模型 ID" min-width="230" show-overflow-tooltip />
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'success' && row.model_id"
              size="small"
              type="primary"
              plain
              @click="startExport(row, 'csv')"
            >
              导出 CSV
            </el-button>
            <el-button v-else size="small" disabled>等待训练完成</el-button>
          </template>
        </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header>
        <div class="section-title">
          <span>预测导出</span>
          <el-button size="small" :loading="loadingExports" @click="loadExports">刷新</el-button>
        </div>
      </template>
      <div class="table-scroll">
        <el-table v-loading="loadingExports" :data="exports" border stripe>
        <el-table-column prop="created_at" label="创建时间" width="190" />
        <el-table-column prop="model_id" label="模型 ID" min-width="230" show-overflow-tooltip />
        <el-table-column prop="file_format" label="格式" width="90" />
        <el-table-column label="状态" width="105">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ exportStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="row_count" label="预测行数" width="100" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button v-if="row.status === 'success'" size="small" type="success" @click="downloadExport(row)">
              下载文件
            </el-button>
            <span v-else class="muted">后台处理中</span>
          </template>
        </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header>
        <div class="section-title">
          <span>操作日志</span>
          <el-button size="small" :loading="loadingLogs" @click="loadLogs">刷新</el-button>
        </div>
      </template>
      <div class="table-scroll">
        <el-table v-loading="loadingLogs" :data="logs" border stripe>
        <el-table-column prop="created_at" label="时间" width="190" />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">{{ operationTypeLabel(row.operation_type) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ exportStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="日志内容" min-width="320" show-overflow-tooltip />
        <el-table-column label="详情" min-width="250" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDetails(row.details) }}</template>
        </el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  downloadMLExport,
  fetchMLDatasets,
  fetchMLExports,
  fetchMLLogs,
  fetchMLRuns,
  startMLExport,
  startMLTraining,
  uploadMLDataset,
} from '../api/ml'

const datasets = ref([])
const runs = ref([])
const exports = ref([])
const logs = ref([])
const loadingDatasets = ref(false)
const loadingRuns = ref(false)
const loadingExports = ref(false)
const loadingLogs = ref(false)
const uploading = ref(false)
const starting = ref(false)
const form = reactive({ datasetKey: 'store_sales', validationDays: 28, horizon: 14 })
let pollTimer = null
let polling = false

const trainableDatasets = computed(() => datasets.value.filter((item) => {
  return item.data_origin !== 'user_upload' || item.status === 'valid'
}))

async function loadDatasets() {
  loadingDatasets.value = true
  try {
    datasets.value = await fetchMLDatasets()
    if (datasets.value.length && !trainableDatasets.value.some((item) => item.key === form.datasetKey)) {
      form.datasetKey = trainableDatasets.value[0]?.key || datasets.value[0].key
    }
  } finally {
    loadingDatasets.value = false
  }
}

async function loadRuns() {
  loadingRuns.value = true
  try {
    const result = await fetchMLRuns({ size: 50 })
    runs.value = result.items || []
  } finally {
    loadingRuns.value = false
  }
}

async function loadExports() {
  loadingExports.value = true
  try {
    const result = await fetchMLExports(50)
    exports.value = result.items || []
  } finally {
    loadingExports.value = false
  }
}

async function loadLogs() {
  loadingLogs.value = true
  try {
    const result = await fetchMLLogs({ size: 100 })
    logs.value = result.items || []
  } finally {
    loadingLogs.value = false
  }
}

async function handleUpload(file) {
  uploading.value = true
  try {
    await uploadMLDataset(file)
    ElMessage.success('数据上传并校验通过，可直接用于训练')
    await Promise.all([loadDatasets(), loadLogs()])
  } finally {
    uploading.value = false
  }
  return false
}

async function startTraining() {
  starting.value = true
  try {
    await startMLTraining(form)
    ElMessage.success('训练任务已进入后台队列')
    await Promise.all([loadRuns(), loadLogs()])
    startPolling()
  } finally {
    starting.value = false
  }
}

async function startExport(row, fileFormat) {
  try {
    await startMLExport({ modelId: row.model_id, runId: row.run_id, fileFormat })
    ElMessage.success('预测导出任务已进入后台队列')
    await Promise.all([loadExports(), loadLogs()])
    startPolling()
  } catch (error) {
    // axios 全局拦截器已经展示具体错误，这里只保留状态不变。
    return error
  }
}

async function downloadExport(row) {
  await downloadMLExport(row.export_id)
  ElMessage.success('预测文件下载已开始')
}

function startPolling() {
  if (pollTimer) return
  pollTimer = window.setInterval(async () => {
    if (polling) return
    polling = true
    try {
      await Promise.all([loadRuns(), loadExports(), loadLogs()])
      const busy = runs.value.some((item) => item.status === 'pending' || item.status === 'running')
        || exports.value.some((item) => item.status === 'pending' || item.status === 'running')
      if (!busy) stopPolling()
    } catch {
      // 请求拦截器负责展示错误；保留轮询，下一轮继续同步后台状态。
    } finally {
      polling = false
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) window.clearInterval(pollTimer)
  pollTimer = null
}

function statusType(status) {
  return { success: 'success', failed: 'danger', running: 'warning', pending: 'info' }[status] || 'info'
}

function statusLabel(status) {
  return { success: '完成', failed: '失败', running: '训练中', pending: '排队中' }[status] || status
}

function exportStatusLabel(status) {
  return { success: '完成', failed: '失败', running: '导出中', pending: '排队中' }[status] || status
}

function datasetStatusType(status) {
  return { valid: 'success', failed: 'danger', validating: 'warning' }[status] || 'info'
}

function datasetStatusLabel(status) {
  return { valid: '校验通过', failed: '校验失败', validating: '校验中' }[status] || status
}

function operationTypeLabel(type) {
  return { data_upload: '数据输入', training: '模型训练', forecast_export: '预测导出' }[type] || type
}

function formatMetric(value) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(2) : '-'
}

function formatPercent(value) {
  return Number.isFinite(Number(value)) ? (Number(value) * 100).toFixed(2) + '%' : '-'
}

function formatDetails(details) {
  return details && Object.keys(details).length ? JSON.stringify(details) : '-'
}

onMounted(async () => {
  await Promise.all([loadDatasets(), loadRuns(), loadExports(), loadLogs()])
  if (runs.value.some((item) => item.status === 'pending' || item.status === 'running')
    || exports.value.some((item) => item.status === 'pending' || item.status === 'running')) startPolling()
})

onBeforeUnmount(stopPolling)
</script>

<style scoped>
.notice {
  margin-bottom: 16px;
}
.section {
  margin-bottom: 16px;
}
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 600;
  flex-wrap: wrap;
}
.upload-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.muted {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}
.dataset-select {
  width: 260px;
}

@media (max-width: 767px) {
  .dataset-select {
    width: 100%;
  }
}
</style>
