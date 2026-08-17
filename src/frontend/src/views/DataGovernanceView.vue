<template>
  <div :class="[{ page: !embedded }, 'governance-page', { 'embedded-view': embedded }]" v-loading="loading">
    <div v-if="!embedded" class="page-head">
      <div>
        <h2>数据治理</h2>
        <p class="desc">检查品牌归属、门店匹配、数据质量和采集来源；无法确认的记录只保留为待处理。</p>
      </div>
      <el-button v-if="canManage" type="primary" :loading="scanning" @click="scan">运行质量扫描</el-button>
    </div>

    <el-alert
      v-if="lastScan"
      class="scan-result"
      type="info"
      :closable="false"
      :title="`最近扫描：${lastScan.status}，发现 ${lastScan.issue_count || 0} 个治理问题`"
    />

    <el-row :gutter="12" class="summary-row">
      <el-col v-for="card in summaryCards" :key="card.label" :xs="12" :sm="6">
        <el-card shadow="never" class="summary-card">
          <div class="card-label">{{ card.label }}</div>
          <div class="card-value">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-tabs v-model="activeTab" class="section">
      <el-tab-pane label="质量问题" name="issues">
        <div class="toolbar">
          <el-select v-model="issueStatus" clearable placeholder="全部状态" @change="loadIssues">
            <el-option label="待处理" value="open" />
            <el-option label="已确认" value="acknowledged" />
            <el-option label="已解决" value="resolved" />
            <el-option label="已忽略" value="ignored" />
          </el-select>
          <el-select v-model="issueSeverity" clearable placeholder="全部级别" @change="loadIssues">
            <el-option label="严重" value="critical" />
            <el-option label="错误" value="error" />
            <el-option label="警告" value="warning" />
            <el-option label="提示" value="info" />
          </el-select>
        </div>
        <div class="table-scroll">
          <el-table :data="issues" border stripe empty-text="暂无治理问题">
          <el-table-column prop="severity" label="级别" width="80">
            <template #default="{ row }"><el-tag :type="severityType(row.severity)">{{ row.severity }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="issue_type" label="问题类型" width="190" />
          <el-table-column prop="source_name" label="来源" width="150" />
          <el-table-column prop="message" label="问题说明" min-width="420" show-overflow-tooltip />
          <el-table-column prop="last_seen" label="最近发现" width="175" />
          <el-table-column v-if="canManage" label="处理" width="190" fixed="right">
            <template #default="{ row }">
              <el-select v-model="row.status" size="small" @change="updateIssue(row)">
                <el-option label="待处理" value="open" />
                <el-option label="已确认" value="acknowledged" />
                <el-option label="已解决" value="resolved" />
                <el-option label="已忽略" value="ignored" />
              </el-select>
            </template>
          </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="门店待匹配" name="stores">
        <el-alert type="info" :closable="false" show-icon title="这是历史别名库。确认别名不会直接把历史原始观测归属到品牌；请在“原始记录映射”中查看来源证据并完成正式决策。" />
        <div class="table-scroll">
          <el-table :data="storeAliases" border stripe empty-text="暂无待匹配门店">
          <el-table-column prop="raw_store_name" label="外部门店名" min-width="250" />
          <el-table-column prop="city" label="城市" width="100" />
          <el-table-column prop="mall_name" label="商场/地点" width="180" />
          <el-table-column prop="source_name" label="来源" width="160" />
          <el-table-column v-if="canManage" label="匹配到主数据" min-width="340">
            <template #default="{ row }">
              <el-select
                v-model="row.selectedStoreId"
                filterable
                remote
                clearable
                reserve-keyword
                placeholder="搜索门店后确认"
                :remote-method="(q) => searchStores(q, row.city)"
                :loading="storeLoading"
                @change="(value) => confirmStoreAlias(row, value)"
              >
                <el-option v-for="store in storeOptions" :key="store.store_id" :label="storeLabel(store)" :value="store.store_id" />
              </el-select>
            </template>
          </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="原始记录映射" name="observations">
        <el-alert type="warning" :closable="false" show-icon title="未确认观测只作为公开竞争线索，不进入正式品牌/门店指标。确认或拒绝均会保留证据、操作者和回算记录。" />
        <div class="toolbar mapping-toolbar">
          <el-select v-model="observationStatus" clearable placeholder="全部映射状态" @change="loadMappingObservations">
            <el-option label="待映射" value="pending" />
            <el-option label="已确认" value="confirmed" />
            <el-option label="已拒绝" value="rejected" />
          </el-select>
          <el-button @click="loadMappingObservations">刷新记录</el-button>
        </div>
        <div class="table-scroll">
          <el-table :data="mappingObservations" border stripe empty-text="当前范围没有可处理的可信原始观测">
            <el-table-column prop="entity_name" label="公开记录" min-width="250" show-overflow-tooltip />
            <el-table-column prop="source_name" label="来源" width="160" />
            <el-table-column prop="observed_date" label="观测日期" width="120" />
            <el-table-column prop="entity_mapping_status" label="映射状态" width="110"><template #default="{ row }"><el-tag :type="mappingStatusType(row.entity_mapping_status)" size="small">{{ row.entity_mapping_status }}</el-tag></template></el-table-column>
            <el-table-column label="当前归属" min-width="180"><template #default="{ row }">{{ row.store_id || row.brand_id || '未确认' }}</template></el-table-column>
            <el-table-column prop="decision_evidence" label="依据" min-width="200" show-overflow-tooltip><template #default="{ row }">{{ row.decision_evidence?.note || '—' }}</template></el-table-column>
            <el-table-column v-if="canManage" label="处理" width="180" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openMapping(row)">查看/决策</el-button><el-button v-if="row.mapping_id" link type="warning" @click="revertMapping(row)">撤销</el-button></template></el-table-column>
          </el-table>
        </div>
        <h3 class="subsection-title">映射回算台账</h3>
        <div class="table-scroll">
          <el-table :data="recalculationRequests" size="small" border empty-text="映射变更后会在此记录受影响快照的指标回算">
            <el-table-column prop="snapshot_id" label="快照" min-width="210" show-overflow-tooltip />
            <el-table-column prop="reason" label="原因" min-width="170" />
            <el-table-column prop="status" label="状态" width="110"><template #default="{ row }"><el-tag :type="mappingStatusType(row.status)" size="small">{{ row.status }}</el-tag></template></el-table-column>
            <el-table-column prop="requested_at" label="请求时间" width="180" />
            <el-table-column prop="error_message" label="错误" min-width="180" show-overflow-tooltip />
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="品牌别名" name="brands">
        <div class="table-scroll">
          <el-table :data="brandAliases" border stripe empty-text="暂无品牌别名">
          <el-table-column prop="brand_id" label="品牌 ID" width="120" />
          <el-table-column prop="alias_text" label="别名" min-width="220" />
          <el-table-column prop="normalized_alias" label="标准化值" min-width="220" />
          <el-table-column prop="source_name" label="来源" width="130" />
          <el-table-column prop="status" label="状态" width="110" />
          <el-table-column prop="confidence" label="置信度" width="100" />
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="采集血缘" name="lineage">
        <div class="table-scroll">
          <el-table :data="lineage" border stripe empty-text="还没有采集血缘记录">
          <el-table-column prop="run_id" label="来源批次" width="210" show-overflow-tooltip />
          <el-table-column prop="trace_id" label="采集任务 ID" width="210" show-overflow-tooltip />
          <el-table-column prop="source_name" label="来源" width="180" />
          <el-table-column prop="source_type" label="类型" width="120" />
          <el-table-column prop="entity_id" label="实体 ID" width="160" />
          <el-table-column prop="record_count" label="记录数" width="90" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="executed_at" label="执行时间" width="180" />
          <el-table-column prop="error_message" label="错误" min-width="240" show-overflow-tooltip />
          </el-table>
        </div>
        <h3 class="subsection-title">原始记录追溯</h3>
        <div class="table-scroll">
          <el-table :data="rawLineage" border stripe empty-text="新的采集任务完成后会在这里显示记录级血缘">
          <el-table-column prop="created_at" label="入库时间" width="180" />
          <el-table-column prop="crawl_job_id" label="采集任务 ID" width="210" show-overflow-tooltip />
          <el-table-column prop="run_id" label="来源批次" width="210" show-overflow-tooltip />
          <el-table-column prop="source_name" label="来源" width="180" />
          <el-table-column prop="record_type" label="记录类型" width="150" />
          <el-table-column prop="record_key" label="记录键" min-width="260" show-overflow-tooltip />
          <el-table-column prop="crawl_date" label="采集日期" width="120" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="mappingDialogOpen" title="原始观测映射决策" width="min(680px, calc(100vw - 32px))" destroy-on-close>
      <template v-if="selectedObservation">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="公开记录">{{ selectedObservation.entity_name }}</el-descriptions-item>
          <el-descriptions-item label="范围">{{ [selectedObservation.city, selectedObservation.mall_name, selectedObservation.category].filter(Boolean).join(' · ') }}</el-descriptions-item>
          <el-descriptions-item label="来源链接"><a v-if="selectedObservation.source_url" :href="selectedObservation.source_url" target="_blank" rel="noreferrer">打开原始链接</a><span v-else>来源未提供链接</span></el-descriptions-item>
        </el-descriptions>
        <el-alert class="dialog-note" type="info" :closable="false" :title="candidateMessage" />
        <el-form label-position="top" class="mapping-form">
          <el-form-item label="确认到真实门店（确认时必填）">
            <el-select v-model="mappingForm.storeId" filterable remote clearable reserve-keyword placeholder="搜索真实门店主数据" :remote-method="searchDecisionStores" :loading="storeLoading">
              <el-option-group v-if="candidateStores.length" label="已确认别名的精确候选">
                <el-option v-for="store in candidateStores" :key="store.store_id" :label="storeLabel(store)" :value="store.store_id" />
              </el-option-group>
              <el-option-group v-if="decisionStoreOptions.length" label="人工搜索结果">
                <el-option v-for="store in decisionStoreOptions" :key="store.store_id" :label="storeLabel(store)" :value="store.store_id" />
              </el-option-group>
            </el-select>
          </el-form-item>
          <el-form-item label="核验依据"><el-input v-model="mappingForm.evidenceNote" type="textarea" :rows="3" maxlength="1000" show-word-limit placeholder="例如：核对原始链接、门店地址和品牌官方门店页后确认" /></el-form-item>
          <el-form-item label="生效日期（可选）"><el-date-picker v-model="mappingForm.effectiveFrom" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        </el-form>
      </template>
      <template #footer><el-button @click="mappingDialogOpen = false">取消</el-button><el-button type="warning" :loading="savingMapping" @click="saveMapping('rejected')">拒绝归属</el-button><el-button type="primary" :loading="savingMapping" :disabled="!mappingForm.storeId" @click="saveMapping('confirmed')">确认映射</el-button></template>
    </el-dialog>

    <el-dialog v-model="revertDialogOpen" title="撤销映射决策" width="min(520px, calc(100vw - 32px))" destroy-on-close>
      <el-form label-position="top"><el-form-item label="撤销依据"><el-input v-model="revertEvidenceNote" type="textarea" :rows="3" maxlength="1000" placeholder="说明为何撤销此映射" /></el-form-item></el-form>
      <template #footer><el-button @click="revertDialogOpen = false">取消</el-button><el-button type="warning" :loading="savingMapping" @click="confirmRevert">确认撤销</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  fetchBrandAliases,
  createMappingDecision,
  fetchMappingCandidates,
  fetchMappingObservations,
  fetchMappingRecalculationRequests,
  fetchGovernanceSummary,
  fetchLineage,
  fetchRawLineage,
  fetchQualityIssues,
  fetchStoreAliases,
  fetchStoreOptions,
  runGovernanceScan,
  revertMappingDecision,
  updateQualityIssue,
  updateStoreAlias,
} from '../api/dataGovernance'
import { usePermissions } from '../composables/usePermissions'
import { useScopeStore } from '../stores/scope'

const props = defineProps({ embedded: { type: Boolean, default: false }, initialTab: { type: String, default: 'issues' } })
const { can } = usePermissions()
const scopeStore = useScopeStore()
const canManage = can('governance.manage')

const loading = ref(false)
const scanning = ref(false)
const activeTab = ref(props.initialTab)
const summary = ref({ records: {}, issue_counts: [], alias_counts: [], latest_scan: null })
const issues = ref([])
const storeAliases = ref([])
const brandAliases = ref([])
const lineage = ref([])
const rawLineage = ref([])
const mappingObservations = ref([])
const recalculationRequests = ref([])
const observationStatus = ref('pending')
const mappingDialogOpen = ref(false)
const revertDialogOpen = ref(false)
const selectedObservation = ref(null)
const selectedMappingId = ref('')
const candidateStores = ref([])
const decisionStoreOptions = ref([])
const candidateMessage = ref('正在加载候选与来源证据…')
const savingMapping = ref(false)
const mappingForm = ref({ storeId: '', evidenceNote: '', effectiveFrom: '' })
const revertEvidenceNote = ref('')
const issueStatus = ref('')
const issueSeverity = ref('')
const storeOptions = ref([])
const storeLoading = ref(false)

const lastScan = computed(() => summary.value.latest_scan)
const openIssueCount = computed(() => summary.value.records?.open_issues || 0)
const pendingStoreCount = computed(() => summary.value.records?.pending_observation_mappings || 0)
const summaryCards = computed(() => [
  { label: '开放治理问题', value: openIssueCount.value },
  { label: '待映射可信观测', value: pendingStoreCount.value },
  { label: '采集血缘记录', value: summary.value.records?.lineage_logs || 0 },
  { label: '可追溯原始行', value: summary.value.records?.raw_lineage_records || 0 },
  { label: '已检查原始记录', value: (summary.value.records?.dp_shop_metrics || 0) + (summary.value.records?.xhs_notes || 0) },
])

async function load() {
  loading.value = true
  try {
    summary.value = await fetchGovernanceSummary()
    await loadActiveTab()
  } finally { loading.value = false }
}

async function loadActiveTab() {
  if (activeTab.value === 'issues') return loadIssues()
  if (activeTab.value === 'stores') {
    const stores = await fetchStoreAliases({ status: 'pending' })
    storeAliases.value = (stores.items || []).map((row) => ({ ...row, selectedStoreId: row.store_id || '' }))
    return
  }
  if (activeTab.value === 'observations') return loadMappingObservations()
  if (activeTab.value === 'brands') { brandAliases.value = await fetchBrandAliases(); return }
  if (activeTab.value === 'lineage') {
    const [logs, rawLogs] = await Promise.all([fetchLineage(), fetchRawLineage()])
    lineage.value = logs
    rawLineage.value = rawLogs
  }
}

async function loadMappingObservations() {
  await scopeStore.load().catch(() => {})
  const [records, requests] = await Promise.all([
    fetchMappingObservations({ scopeId: scopeStore.currentId, mappingStatus: observationStatus.value }),
    fetchMappingRecalculationRequests({ scopeId: scopeStore.currentId }),
  ])
  mappingObservations.value = (records.items || []).map((row) => ({
    ...row,
    entity_name: row.payload?.shop_name || row.payload?.title || row.source_record_key,
  }))
  recalculationRequests.value = requests
}

async function loadIssues() {
  const result = await fetchQualityIssues({ status: issueStatus.value, severity: issueSeverity.value })
  issues.value = result.items || []
}

async function scan() {
  scanning.value = true
  try {
    await runGovernanceScan()
    await load()
    ElMessage.success('数据质量扫描完成')
  } finally {
    scanning.value = false
  }
}

async function updateIssue(row) {
  await updateQualityIssue(row.issue_id, { status: row.status, resolution_note: '' })
  ElMessage.success('问题状态已更新')
  await load()
}

async function searchStores(query, city) {
  storeLoading.value = true
  try {
    storeOptions.value = await fetchStoreOptions({ q: query, city })
  } finally {
    storeLoading.value = false
  }
}

async function confirmStoreAlias(row, storeId) {
  if (!storeId) return
  await updateStoreAlias(row.alias_id, { store_id: storeId, status: 'confirmed', note: '在数据治理页面人工确认' })
  ElMessage.success('门店匹配已确认')
  await load()
}

async function openMapping(row) {
  selectedObservation.value = row
  mappingForm.value = { storeId: row.store_id || '', evidenceNote: '', effectiveFrom: '' }
  candidateStores.value = []
  decisionStoreOptions.value = []
  candidateMessage.value = '正在加载候选与来源证据…'
  mappingDialogOpen.value = true
  try {
    const result = await fetchMappingCandidates(row.observation_id)
    candidateStores.value = result.items || []
    candidateMessage.value = result.message || '请核对来源证据后再决策。'
  } catch { candidateMessage.value = '候选加载失败；仍可通过人工搜索门店后完成决策。' }
}

async function searchDecisionStores(query) {
  storeLoading.value = true
  try { decisionStoreOptions.value = await fetchStoreOptions({ q: query }) } finally { storeLoading.value = false }
}

async function saveMapping(mappingStatus) {
  if (!selectedObservation.value || mappingForm.value.evidenceNote.trim().length < 3) {
    ElMessage.warning('请填写至少 3 个字符的核验依据')
    return
  }
  savingMapping.value = true
  try {
    const result = await createMappingDecision(selectedObservation.value.observation_id, {
      mapping_status: mappingStatus,
      store_id: mappingStatus === 'confirmed' ? mappingForm.value.storeId : undefined,
      evidence_note: mappingForm.value.evidenceNote,
      effective_from: mappingForm.value.effectiveFrom || undefined,
    })
    mappingDialogOpen.value = false
    const failures = result.recalculation?.failed?.length || 0
    ElMessage[failures ? 'warning' : 'success'](failures ? '映射已保存，但部分快照回算失败，请查看台账' : '映射已保存，受影响快照已完成回算')
    await load()
  } finally { savingMapping.value = false }
}

function revertMapping(row) {
  selectedMappingId.value = row.mapping_id
  revertEvidenceNote.value = ''
  revertDialogOpen.value = true
}

async function confirmRevert() {
  if (revertEvidenceNote.value.trim().length < 3) { ElMessage.warning('请填写至少 3 个字符的撤销依据'); return }
  savingMapping.value = true
  try {
    await revertMappingDecision(selectedMappingId.value, { evidence_note: revertEvidenceNote.value })
    revertDialogOpen.value = false
    ElMessage.success('映射决策已撤销，并已登记受影响快照回算')
    await load()
  } finally { savingMapping.value = false }
}

function storeLabel(store) {
  return `${store.store_name || store.store_id} · ${store.city || '-'} · ${store.mall_name || store.address || '-'}`
}

function severityType(value) {
  return { critical: 'danger', error: 'danger', warning: 'warning', info: 'info' }[value] || 'info'
}
function mappingStatusType(value) {
  return { confirmed: 'success', completed: 'success', pending: 'warning', running: 'warning', rejected: 'info', revoked: 'info', failed: 'danger', legacy_unclassified: 'danger' }[value] || 'info'
}

watch(() => props.initialTab, (value) => { activeTab.value = value || 'issues' })
watch(activeTab, () => { if (!loading.value) loadActiveTab() })
watch(() => scopeStore.currentId, () => { if (activeTab.value === 'observations' && !loading.value) loadMappingObservations() })
onMounted(load)
</script>

<style scoped>
.page-head h2 { margin: 0 0 8px; }
.desc { margin: 0; color: #909399; font-size: 13px; }
.scan-result { margin-bottom: 12px; }
.summary-row { margin-bottom: 16px; }
.summary-card { min-height: 94px; }
.card-label { color: #909399; font-size: 13px; }
.card-value { margin-top: 10px; color: #303133; font-size: 25px; font-weight: 700; }
.section { background: #fff; }
.toolbar { align-items: center; }
.subsection-title { margin: 24px 0 12px; font-size: 15px; }
</style>
