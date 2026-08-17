<template>
  <section class="snapshot-panel">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="正式看板、报告与告警只应引用 ready 或 published 快照。partial/failed 快照保留用于排障，不会被当作完整数据。"
    />
    <div class="panel-toolbar">
      <div class="source-health" aria-label="当前来源健康度">
        <el-tag v-for="source in sourceHealth" :key="source.source_name" :type="sourceType(source)" effect="plain">
          {{ sourceLabel(source) }}
        </el-tag>
      </div>
      <el-button :loading="loading" @click="load"><el-icon><Refresh /></el-icon>刷新快照</el-button>
    </div>

    <div class="table-scroll">
      <el-table :data="snapshots" v-loading="loading" border stripe empty-text="当前范围尚无采集快照">
        <el-table-column prop="snapshot_id" label="快照 ID" min-width="210" show-overflow-tooltip />
        <el-table-column prop="observed_at" label="数据截止时间" width="180">
          <template #default="{ row }">{{ formatTime(row.observed_at) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }"><el-tag :type="snapshotType(row.status)" size="small">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="quality_grade" label="质量等级" width="100" />
        <el-table-column prop="data_mode" label="数据模式" min-width="155">
          <template #default="{ row }">{{ dataModeLabel(row.data_mode) }}</template>
        </el-table-column>
        <el-table-column label="来源覆盖" min-width="145">
          <template #default="{ row }">{{ coverageLabel(row.source_coverage) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row.snapshot_id)">查看依据</el-button>
            <el-button v-if="canPublish && row.status === 'ready'" link type="success" :loading="publishingId === row.snapshot_id" @click="publish(row.snapshot_id)">发布</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-drawer v-model="drawerOpen" title="快照来源与质量依据" size="min(540px, 100vw)">
      <template v-if="selected">
        <el-descriptions :column="1" border size="small" class="snapshot-detail">
          <el-descriptions-item label="快照">{{ selected.snapshot_id }}</el-descriptions-item>
          <el-descriptions-item label="范围">{{ [selected.city, selected.mall_name, selected.category].filter(Boolean).join(' · ') }}</el-descriptions-item>
          <el-descriptions-item label="截止时间">{{ formatTime(selected.observed_at) }}</el-descriptions-item>
          <el-descriptions-item label="质量">{{ selected.status }} · {{ selected.quality_grade }} · {{ dataModeLabel(selected.data_mode) }}</el-descriptions-item>
          <el-descriptions-item label="失败原因">{{ selected.failure_reason || '无' }}</el-descriptions-item>
        </el-descriptions>
        <h3>来源执行结果</h3>
        <el-timeline>
          <el-timeline-item v-for="source in selected.source_results || []" :key="source.source_name" :type="sourceType(source)" :timestamp="formatTime(source.observed_at)">
            <strong>{{ source.source_name }}</strong>
            <p>状态：{{ source.status }}；校验记录：{{ source.validated_count }}；{{ source.failure_reason || '无失败原因' }}</p>
          </el-timeline-item>
        </el-timeline>
      </template>
      <el-skeleton v-else :rows="8" animated />
    </el-drawer>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchSnapshot, fetchSnapshots, fetchSourceHealth, publishSnapshot } from '../api/snapshots'
import { usePermissions } from '../composables/usePermissions'

const props = defineProps({ scopeId: { type: String, default: '' } })
const { can } = usePermissions()
const canPublish = can('monitoring.manage')
const snapshots = ref([])
const sourceHealth = ref([])
const loading = ref(false)
const publishingId = ref('')
const drawerOpen = ref(false)
const selected = ref(null)

function sourceType(source) {
  const status = source?.status || source?.result?.status
  return ({ success: 'success', ready: 'success', published: 'success', empty_validated: 'info', collecting: 'warning', partial: 'warning', failed: 'danger', stale: 'warning', skipped: 'info' })[status] || 'info'
}
function sourceLabel(source) {
  const result = source.result
  return `${source.source_name}：${result?.status || '未执行'}`
}
function snapshotType(status) { return sourceType({ status }) }
function dataModeLabel(mode) { return ({ multi_source: '多来源', dianping_single_source: '点评单源', single_source: '单来源', raw_only: '仅原始数据' })[mode] || mode || '-' }
function coverageLabel(coverage) {
  if (!coverage || typeof coverage !== 'object') return '-'
  return `${coverage.success_count ?? 0} / ${coverage.expected_count ?? 0} 个来源成功`
}
function formatTime(value) { return value ? new Date(value).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' }) : '-' }

async function load() {
  if (!props.scopeId) { snapshots.value = []; sourceHealth.value = []; return }
  loading.value = true
  try {
    const [items, health] = await Promise.all([fetchSnapshots({ scopeId: props.scopeId }), fetchSourceHealth(props.scopeId)])
    snapshots.value = items
    sourceHealth.value = health
  } finally { loading.value = false }
}
async function openDetail(snapshotId) {
  selected.value = null
  drawerOpen.value = true
  try { selected.value = await fetchSnapshot(snapshotId) } catch { drawerOpen.value = false }
}
async function publish(snapshotId) {
  publishingId.value = snapshotId
  try { await publishSnapshot(snapshotId); ElMessage.success('快照已发布，后续正式页面将引用此版本'); await load() } finally { publishingId.value = '' }
}

watch(() => props.scopeId, load, { immediate: true })
</script>

<style scoped>
.snapshot-panel { display: flex; flex-direction: column; gap: 14px; }.panel-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; }.source-health { display: flex; flex: 1; flex-wrap: wrap; gap: 8px; }.snapshot-detail { margin-bottom: 20px; }.snapshot-panel h3 { margin: 18px 0 10px; color: var(--bp-text-strong); font-size: 15px; }.snapshot-panel p { margin: 4px 0 0; color: var(--bp-text-secondary); font-size: 12px; line-height: 1.5; } @media (max-width: 767px) { .panel-toolbar { align-items: flex-start; flex-direction: column; } }
</style>
