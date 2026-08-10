<template>
  <div class="page governance-page" v-loading="loading">
    <div class="page-head">
      <div>
        <h2>数据治理</h2>
        <p class="desc">检查品牌归属、门店匹配、数据质量和采集来源；无法确认的记录只保留为待处理。</p>
      </div>
      <el-button type="primary" :loading="scanning" @click="scan">运行质量扫描</el-button>
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
          <el-table-column label="处理" width="190" fixed="right">
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
        <div class="table-scroll">
          <el-table :data="storeAliases" border stripe empty-text="暂无待匹配门店">
          <el-table-column prop="raw_store_name" label="外部门店名" min-width="250" />
          <el-table-column prop="city" label="城市" width="100" />
          <el-table-column prop="mall_name" label="商场/地点" width="180" />
          <el-table-column prop="source_name" label="来源" width="160" />
          <el-table-column label="匹配到主数据" min-width="340">
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
          <el-table-column prop="source_name" label="来源" width="180" />
          <el-table-column prop="source_type" label="类型" width="120" />
          <el-table-column prop="entity_id" label="实体 ID" width="160" />
          <el-table-column prop="record_count" label="记录数" width="90" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="executed_at" label="执行时间" width="180" />
          <el-table-column prop="error_message" label="错误" min-width="240" show-overflow-tooltip />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  fetchBrandAliases,
  fetchGovernanceSummary,
  fetchLineage,
  fetchQualityIssues,
  fetchStoreAliases,
  fetchStoreOptions,
  runGovernanceScan,
  updateQualityIssue,
  updateStoreAlias,
} from '../api/dataGovernance'

const loading = ref(false)
const scanning = ref(false)
const activeTab = ref('issues')
const summary = ref({ records: {}, issue_counts: [], alias_counts: [], latest_scan: null })
const issues = ref([])
const storeAliases = ref([])
const brandAliases = ref([])
const lineage = ref([])
const issueStatus = ref('')
const issueSeverity = ref('')
const storeOptions = ref([])
const storeLoading = ref(false)

const lastScan = computed(() => summary.value.latest_scan)
const openIssueCount = computed(() => summary.value.records?.open_issues || 0)
const pendingStoreCount = computed(() => {
  const item = (summary.value.alias_counts || []).find((x) => x.kind === 'store' && x.status === 'pending')
  return item?.count || 0
})
const summaryCards = computed(() => [
  { label: '开放治理问题', value: openIssueCount.value },
  { label: '待匹配门店别名', value: pendingStoreCount.value },
  { label: '采集血缘记录', value: summary.value.records?.lineage_logs || 0 },
  { label: '已检查原始记录', value: (summary.value.records?.dp_shop_metrics || 0) + (summary.value.records?.xhs_notes || 0) },
])

async function load() {
  loading.value = true
  try {
    const [s, i, stores, brands, logs] = await Promise.all([
      fetchGovernanceSummary(),
      fetchQualityIssues({ status: issueStatus.value, severity: issueSeverity.value }),
      fetchStoreAliases({ status: 'pending' }),
      fetchBrandAliases(),
      fetchLineage(),
    ])
    summary.value = s
    issues.value = i.items || []
    storeAliases.value = (stores.items || []).map((row) => ({ ...row, selectedStoreId: row.store_id || '' }))
    brandAliases.value = brands
    lineage.value = logs
  } finally {
    loading.value = false
  }
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

function storeLabel(store) {
  return `${store.store_name || store.store_id} · ${store.city || '-'} · ${store.mall_name || store.address || '-'}`
}

function severityType(value) {
  return { critical: 'danger', error: 'danger', warning: 'warning', info: 'info' }[value] || 'info'
}

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
</style>
