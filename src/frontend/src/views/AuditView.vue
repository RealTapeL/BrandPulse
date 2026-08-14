<template>
  <div class="page audit-page" v-loading="loading">
    <div class="page-header">
      <h2>操作审计</h2>
      <p class="desc">记录 API 操作者、动作、结果和请求 ID；不保存密码、Token、请求正文或上传文件。</p>
    </div>

    <el-alert
      v-if="configuration"
      class="configuration-alert"
      :type="configuration.production_ready ? 'success' : 'warning'"
      :closable="false"
      show-icon
      :title="configuration.production_ready ? '生产基础配置检查通过' : `还有 ${failedChecks.length} 项生产配置未完成`"
    >
      <template #default>
        <div class="configuration-checks">
          <span v-for="item in configuration.checks" :key="item.key">
            <el-tag :type="checkType(item.status)" size="small">{{ item.label }}</el-tag>
            {{ item.message }}
          </span>
        </div>
      </template>
    </el-alert>

    <el-card shadow="never" class="section">
      <div class="toolbar audit-toolbar">
        <el-input v-model="filters.actor_id" clearable placeholder="操作者" @keyup.enter="search" />
        <el-select v-model="filters.method" clearable placeholder="请求方法">
          <el-option v-for="method in methods" :key="method" :label="method" :value="method" />
        </el-select>
        <el-select v-model="filters.outcome" clearable placeholder="执行结果">
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failure" />
        </el-select>
        <el-input v-model="filters.action" clearable placeholder="动作或路由" @keyup.enter="search" />
        <el-input v-model="filters.request_id" clearable placeholder="请求 ID" @keyup.enter="search" />
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <div class="table-scroll">
        <el-table :data="items" border stripe empty-text="暂无审计记录">
          <el-table-column prop="created_at" label="时间" width="180" />
          <el-table-column prop="actor_id" label="操作者" width="140" show-overflow-tooltip />
          <el-table-column prop="method" label="方法" width="82" />
          <el-table-column prop="route" label="动作路由" min-width="250" show-overflow-tooltip />
          <el-table-column label="结果" width="90">
            <template #default="{ row }">
              <el-tag :type="row.outcome === 'success' ? 'success' : 'danger'">
                {{ row.outcome === 'success' ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status_code" label="状态码" width="90" />
          <el-table-column label="耗时" width="105">
            <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
          </el-table-column>
          <el-table-column prop="client_ip" label="客户端 IP" width="135" />
          <el-table-column prop="request_id" label="请求 ID" min-width="240" show-overflow-tooltip />
        </el-table>
      </div>

      <div class="pagination-row">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          layout="total, sizes, prev, pager, next"
          :page-sizes="[20, 50, 100]"
          :total="total"
          @current-change="load"
          @size-change="changeSize"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { fetchAuditEvents, fetchConfigurationStatus } from '../api/audit'

const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
const filters = reactive({ actor_id: '', method: '', outcome: '', action: '', request_id: '' })
const items = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const loading = ref(false)
const configuration = ref(null)
const failedChecks = computed(() => (configuration.value?.checks || []).filter((item) => item.status === 'fail'))

function queryParams() {
  return {
    actor_id: filters.actor_id || undefined,
    method: filters.method || undefined,
    outcome: filters.outcome || undefined,
    action: filters.action || undefined,
    request_id: filters.request_id || undefined,
    page: page.value,
    size: size.value,
  }
}

async function load() {
  loading.value = true
  try {
    const result = await fetchAuditEvents(queryParams())
    items.value = result.items || []
    total.value = result.total || 0
  } finally {
    loading.value = false
  }
}

function search() { page.value = 1; load() }
function changeSize() { page.value = 1; load() }
function reset() {
  Object.assign(filters, { actor_id: '', method: '', outcome: '', action: '', request_id: '' })
  search()
}
function formatDuration(value) {
  const duration = Number(value || 0)
  return duration >= 1000 ? `${(duration / 1000).toFixed(2)} s` : `${duration.toFixed(1)} ms`
}
function checkType(status) { return { pass: 'success', warning: 'warning', fail: 'danger' }[status] || 'info' }

onMounted(async () => {
  const [, config] = await Promise.all([load(), fetchConfigurationStatus()])
  configuration.value = config
})
</script>

<style scoped>
.section { margin-bottom: 16px; }
.configuration-alert { margin-bottom: 16px; }
.configuration-checks { display: grid; gap: 8px; margin-top: 8px; }
.configuration-checks span { display: flex; align-items: center; gap: 8px; line-height: 1.5; }
.audit-toolbar { display: grid; grid-template-columns: repeat(5, minmax(130px, 1fr)) auto auto; gap: 10px; margin-bottom: 16px; }
.pagination-row { display: flex; justify-content: flex-end; margin-top: 16px; overflow-x: auto; }

@media (max-width: 1199px) {
  .audit-toolbar { grid-template-columns: repeat(3, minmax(150px, 1fr)); }
}

@media (max-width: 767px) {
  .audit-toolbar { grid-template-columns: 1fr; }
  .pagination-row { justify-content: flex-start; }
}
</style>
