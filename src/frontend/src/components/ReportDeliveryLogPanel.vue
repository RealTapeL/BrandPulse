<template>
  <el-card shadow="never" class="report-delivery-panel">
    <template #header><div class="panel-head"><div><h2>报告分发记录</h2><p>仅展示经审核后创建的真实投递任务；失败项按指数退避重试。</p></div><el-button size="small" :loading="loading" @click="load">刷新</el-button></div></template>
    <div class="table-scroll"><el-table v-loading="loading" :data="deliveries" border stripe empty-text="暂无报告分发记录"><el-table-column prop="updated_at" label="更新时间" width="180" /><el-table-column prop="report_id" label="报告" min-width="180" show-overflow-tooltip /><el-table-column label="范围" min-width="180"><template #default="{ row }">{{ row.city || '-' }} · {{ row.mall_name || '-' }} · {{ row.category || '-' }}</template></el-table-column><el-table-column prop="channel" label="渠道" width="100" /><el-table-column prop="recipient" label="接收方" min-width="180" show-overflow-tooltip /><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag></template></el-table-column><el-table-column prop="attempt_count" label="尝试" width="80" /><el-table-column prop="last_error" label="错误" min-width="220" show-overflow-tooltip /></el-table></div>
  </el-card>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { fetchAllReportDeliveries } from '../api/reports'

const deliveries = ref([]); const loading = ref(false)
function statusType(value) { return { sent: 'success', retry: 'warning', pending: 'info', sending: 'warning', failed: 'danger', cancelled: 'info' }[value] || 'info' }
function statusLabel(value) { return { sent: '已发送', retry: '待重试', pending: '待发送', sending: '发送中', failed: '失败', cancelled: '已取消' }[value] || value }
async function load() { loading.value = true; try { deliveries.value = (await fetchAllReportDeliveries()).items || [] } finally { loading.value = false } }
onMounted(load)
</script>

<style scoped>
.panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }.panel-head h2 { margin: 0; color: var(--bp-text-strong); font-size: 15px; }.panel-head p { margin: 4px 0 0; color: var(--bp-text-muted); font-size: 12px; } @media (max-width: 767px) { .panel-head { flex-direction: column; } }
</style>
