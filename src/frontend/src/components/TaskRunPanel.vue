<template>
  <div class="task-run-panels">
    <el-card shadow="never" class="run-panel">
      <template #header><div class="run-panel__header"><div><h2>Agent 后台任务</h2><p>当前账号可见的真实 Agent 任务记录。</p></div><el-button size="small" :loading="loading" @click="load">刷新</el-button></div></template>
      <div class="table-scroll"><el-table :data="agentTasks" max-height="280" empty-text="暂无 Agent 任务记录"><el-table-column prop="id" label="任务 ID" min-width="170" show-overflow-tooltip /><el-table-column prop="input" label="任务说明" min-width="220" show-overflow-tooltip /><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag></template></el-table-column><el-table-column prop="updated_at" label="更新时间" width="180" /></el-table></div>
    </el-card>
    <el-card shadow="never" class="run-panel">
      <template #header><div class="run-panel__header"><div><h2>报告生成记录</h2><p>报告任务会先经过同一套数据新鲜度校验。</p></div></div></template>
      <div class="table-scroll"><el-table :data="reports" max-height="280" empty-text="暂无报告生成记录"><el-table-column prop="created_at" label="创建时间" width="180" /><el-table-column prop="file_format" label="格式" width="85" /><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag></template></el-table-column><el-table-column prop="error" label="错误或说明" min-width="230" show-overflow-tooltip /></el-table></div>
    </el-card>
    <el-alert class="run-limit" type="info" :closable="false" show-icon title="采集任务的最近结果在“采集计划”中展示；当前后端没有统一的 ML 任务日志接口，因此不会在这里伪造 ML 运行记录。" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { listTasks } from '../api/agent'
import { fetchReports } from '../api/reports'

const agentTasks = ref([]); const reports = ref([]); const loading = ref(false)
function statusType(status) { return ({ success: 'success', completed: 'success', failed: 'danger', running: 'warning', pending: 'info', skipped: 'warning' })[status] || 'info' }
function statusLabel(status) { return ({ success: '完成', completed: '完成', failed: '失败', running: '运行中', pending: '排队中', skipped: '已跳过' })[status] || status || '未知' }
async function load() { loading.value = true; try { const [tasks, reportRows] = await Promise.all([listTasks({ size: 50 }), fetchReports()]); agentTasks.value = tasks.items || []; reports.value = reportRows.items || [] } finally { loading.value = false } }
onMounted(load)
</script>

<style scoped>
.task-run-panels { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }.run-panel__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }.run-panel h2 { margin: 0; color: var(--bp-text-strong); font-size: 15px; }.run-panel p { margin: 4px 0 0; color: var(--bp-text-muted); font-size: 12px; }.run-limit { grid-column: 1 / -1; } @media (max-width: 1023px) { .task-run-panels { grid-template-columns: 1fr; } }
</style>
