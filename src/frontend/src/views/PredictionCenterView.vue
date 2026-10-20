<template>
  <div class="page prediction-page">
    <div class="page-header">
      <div>
        <h2>预测中心</h2>
        <p class="desc">只展示通过真实快照准入的数据预测；数据未就绪时明确显示缺口，不生成模拟结果。</p>
      </div>
      <el-button :loading="loading" @click="loadAll">重新检查</el-button>
    </div>
    <el-alert
      v-if="scopeStore.current"
      :title="'当前范围：' + scopeStore.label + ' · 目标：未来 7 天新增点评评价数'"
      type="info"
      :closable="false"
      show-icon
      class="section"
    />
    <el-empty v-else description="请选择监测范围后查看预测准入状态" />

    <template v-if="scopeStore.current">
      <el-card shadow="never" class="section">
        <template #header>
          <div class="section-title">
            <span>预测数据准入</span>
            <el-tag :type="readiness?.status === 'ready' ? 'success' : 'warning'">
              {{ readiness?.status === 'ready' ? '可以训练' : '数据未就绪' }}
            </el-tag>
          </div>
        </template>
        <div v-loading="loading" class="readiness-grid">
          <div class="readiness-item"><span>可比较周期</span><strong>{{ readiness?.eligible_periods ?? '-' }} / {{ readiness?.required_periods ?? 12 }}</strong></div>
          <div class="readiness-item"><span>最低来源覆盖率</span><strong>{{ formatPercent(readiness?.source_coverage) }}</strong></div>
          <div class="readiness-item"><span>训练时间切分</span><strong>按时间顺序</strong></div>
          <div class="readiness-item"><span>最新输入快照</span><strong class="mono">{{ readiness?.latest_snapshot_id || '-' }}</strong></div>
        </div>
        <el-alert
          v-if="readiness?.blockers?.length"
          class="readiness-alert"
          type="warning"
          :closable="false"
          title="当前不会创建训练任务"
        >
          <ul class="blocker-list">
            <li v-for="blocker in readiness.blockers" :key="blocker.code">{{ blocker.message }}</li>
          </ul>
        </el-alert>
        <el-button v-if="canManage && readiness?.status === 'ready'" type="primary" :loading="starting" @click="startReviewTraining">
          训练点评增量预测
        </el-button>
      </el-card>

      <el-card shadow="never" class="section">
        <template #header><div class="section-title"><span>可追溯时序</span><span class="muted">每个点都来自一个 ready/published 快照</span></div></template>
        <div class="table-scroll">
          <el-table :data="readiness?.series || []" border stripe>
            <el-table-column prop="period" label="周期" width="130" />
            <el-table-column prop="value" label="新增点评评价数" width="160" />
            <el-table-column prop="source_coverage" label="来源覆盖率" width="130">
              <template #default="{ row }">{{ formatPercent(row.source_coverage) }}</template>
            </el-table-column>
            <el-table-column prop="snapshot_id" label="输入快照" min-width="280" show-overflow-tooltip />
            <el-table-column prop="quality_grade" label="质量" width="90" />
          </el-table>
        </div>
      </el-card>

      <el-card shadow="never" class="section">
        <template #header><div class="section-title"><span>模型版本与发布</span><span class="muted">发布后自动写入模型路由，旧版本保留可回滚</span></div></template>
        <div class="table-scroll">
          <el-table v-loading="loadingModels" :data="models" border stripe>
            <el-table-column prop="model_id" label="模型" min-width="260" show-overflow-tooltip />
            <el-table-column prop="model_family" label="算法" width="170" />
            <el-table-column prop="status" label="状态" width="130">
              <template #default="{ row }"><el-tag :type="modelStatusType(row.status)">{{ modelStatusLabel(row.status) }}</el-tag></template>
            </el-table-column>
            <el-table-column label="模型 / 基线 WAPE" width="180">
              <template #default="{ row }">{{ formatPercent(row.metrics?.wape) }} / {{ formatPercent(row.baseline_metrics?.wape) }}</template>
            </el-table-column>
            <el-table-column prop="data_origin" label="数据层" width="160" />
            <el-table-column label="操作" width="180">
              <template #default="{ row }">
                <el-button v-if="canManage && ['evaluated', 'pending_approval', 'degraded'].includes(row.status)" size="small" type="primary" @click="publish(row)">发布</el-button>
                <el-button v-if="canManage && ['published', 'monitoring'].includes(row.status)" size="small" type="warning" plain @click="retire(row)">停用</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!loadingModels && !models.length" :image-size="70" description="还没有完成评估的模型版本" />
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useScopeStore } from '../stores/scope'
import { usePermissions } from '../composables/usePermissions'
import {
  fetchForecastReadiness,
  fetchRegisteredModels,
  publishRegisteredModel,
  retireRegisteredModel,
  startMLTraining,
} from '../api/ml'

const scopeStore = useScopeStore()
const { can } = usePermissions()
const canManage = computed(() => can('ml.manage'))
const loading = ref(false)
const loadingModels = ref(false)
const starting = ref(false)
const readiness = ref(null)
const models = ref([])

function formatPercent(value) {
  return value === null || value === undefined ? '-' : (Number(value) * 100).toFixed(1) + '%'
}
function modelStatusLabel(value) {
  return ({ draft: '草稿', trained: '已训练', evaluated: '已评估', pending_approval: '待审批', monitoring: '监控中', published: '已发布', degraded: '已降级', retired: '已停用', archived: '已归档' }[value] || value || '-')
}
function modelStatusType(value) {
  return ['monitoring', 'published'].includes(value) ? 'success' : ['degraded', 'retired'].includes(value) ? 'warning' : value === 'evaluated' ? 'primary' : 'info'
}
async function loadReadiness() {
  if (!scopeStore.currentId) return
  readiness.value = await fetchForecastReadiness({ scopeId: scopeStore.currentId })
}
async function loadModels() {
  if (!scopeStore.currentId) return
  loadingModels.value = true
  try { models.value = (await fetchRegisteredModels({ scopeId: scopeStore.currentId })).items || [] } finally { loadingModels.value = false }
}
async function loadAll() {
  loading.value = true
  try { await Promise.all([loadReadiness(), loadModels()]) } finally { loading.value = false }
}
async function startReviewTraining() {
  starting.value = true
  try {
    await startMLTraining({ datasetKey: 'trusted_dianping_reviews', scopeId: scopeStore.currentId, targetMetric: 'dp_review_count_delta', entityType: 'scope', horizon: 7 })
    ElMessage.success('点评增量预测训练已进入后台队列')
    await loadModels()
  } finally { starting.value = false }
}
async function publish(row) {
  await publishRegisteredModel(row.model_version_id)
  ElMessage.success('模型已发布并接入当前预测路由')
  await loadModels()
}
async function retire(row) {
  await ElMessageBox.confirm('停用后当前路由将不可用，是否继续？', '确认停用', { type: 'warning' })
  await retireRegisteredModel(row.model_version_id)
  ElMessage.success('模型已停用')
  await loadModels()
}
watch(() => scopeStore.currentId, () => loadAll().catch(() => {}))
onMounted(() => { scopeStore.load().then(loadAll).catch(() => {}) })
</script>

<style scoped>
.section { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.readiness-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.readiness-item { min-width: 0; padding: 14px; border: 1px solid var(--bp-card-border); border-radius: 8px; background: #fafcff; }
.readiness-item span { display: block; color: var(--bp-text-muted); font-size: 12px; margin-bottom: 7px; }
.readiness-item strong { display: block; color: var(--bp-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.readiness-alert { margin: 12px 0 16px; }
.blocker-list { margin: 0; padding-left: 18px; }
.blocker-list li + li { margin-top: 4px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
@media (max-width: 900px) { .readiness-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .readiness-grid { grid-template-columns: 1fr; } }
</style>
