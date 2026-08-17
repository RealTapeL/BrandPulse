<template>
  <section class="cases-panel">
    <div class="cases-toolbar">
      <el-select v-model="status" clearable placeholder="全部状态" class="filter-control" @change="load"><el-option v-for="item in statuses" :key="item.value" :label="item.label" :value="item.value" /></el-select>
      <el-button :loading="loading" @click="load">刷新</el-button>
      <el-button v-if="canManage" type="primary" @click="createOpen = true">新建事项</el-button>
    </div>
    <div class="table-scroll">
      <el-table v-loading="loading" :data="cases" border stripe empty-text="暂无待处理事项">
        <el-table-column prop="title" label="事项" min-width="240" show-overflow-tooltip />
        <el-table-column label="类型" width="120"><template #default="{ row }">{{ typeLabel(row.case_type) }}</template></el-table-column>
        <el-table-column label="优先级" width="95"><template #default="{ row }"><el-tag :type="priorityType(row.priority)" size="small">{{ priorityLabel(row.priority) }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="125"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="owner_id" label="负责人" width="120" show-overflow-tooltip><template #default="{ row }">{{ row.owner_id || '未分配' }}</template></el-table-column>
        <el-table-column prop="due_at" label="截止时间" width="165" />
        <el-table-column label="操作" width="130" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openDetail(row)">查看</el-button><el-button v-if="canManage && !['resolved', 'closed'].includes(row.status)" link type="primary" @click="advance(row)">处理</el-button></template></el-table-column>
      </el-table>
    </div>

    <el-drawer v-model="detailOpen" :title="detail?.title || '事项详情'" size="min(560px, 100%)">
      <template v-if="detail">
        <el-descriptions :column="1" border size="small"><el-descriptions-item label="来源">{{ detail.source_type }} · {{ detail.source_id }}</el-descriptions-item><el-descriptions-item label="范围">{{ detail.scope_id || '未绑定范围' }}</el-descriptions-item><el-descriptions-item label="状态">{{ statusLabel(detail.status) }}</el-descriptions-item><el-descriptions-item label="反馈">{{ feedbackLabel(detail.feedback) }}</el-descriptions-item><el-descriptions-item label="说明">{{ detail.description || '-' }}</el-descriptions-item></el-descriptions>
        <el-divider>证据</el-divider><pre class="evidence">{{ JSON.stringify(detail.evidence || {}, null, 2) }}</pre>
        <el-divider>处理记录</el-divider><el-timeline><el-timeline-item v-for="event in detail.events || []" :key="event.event_id" :timestamp="event.created_at"><strong>{{ event.action }}</strong><p>{{ event.note || '无备注' }}</p></el-timeline-item></el-timeline>
      </template>
    </el-drawer>

    <el-dialog v-model="createOpen" title="新建业务事项" width="min(560px, calc(100vw - 32px))">
      <el-form label-position="top"><el-form-item label="标题" required><el-input v-model="form.title" /></el-form-item><el-form-item label="类型"><el-select v-model="form.case_type"><el-option label="数据质量" value="data_quality" /><el-option label="采集异常" value="collection_exception" /><el-option label="品牌风险" value="brand_risk" /><el-option label="招商机会" value="opportunity" /><el-option label="人工事项" value="manual" /></el-select></el-form-item><el-form-item label="优先级"><el-select v-model="form.priority"><el-option label="高" value="high" /><el-option label="普通" value="normal" /><el-option label="低" value="low" /></el-select></el-form-item><el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item></el-form>
      <template #footer><el-button @click="createOpen = false">取消</el-button><el-button type="primary" :loading="saving" @click="createManual">创建</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createCase, fetchCase, fetchCases, updateCase } from '../api/cases'
import { useScopeStore } from '../stores/scope'
import { usePermissions } from '../composables/usePermissions'

const scopeStore = useScopeStore(); const { can } = usePermissions(); const canManage = can('case.manage')
const cases = ref([]); const status = ref(''); const loading = ref(false); const saving = ref(false); const detail = ref(null); const detailOpen = ref(false); const createOpen = ref(false)
const form = reactive({ title: '', case_type: 'manual', priority: 'normal', description: '' })
const statuses = [{ value: 'open', label: '待处理' }, { value: 'acknowledged', label: '已确认' }, { value: 'investigating', label: '调查中' }, { value: 'action_planned', label: '待执行' }, { value: 'in_progress', label: '处理中' }, { value: 'resolved', label: '已解决' }, { value: 'closed', label: '已关闭' }]
function statusLabel(value) { return Object.fromEntries(statuses.map((item) => [item.value, item.label]))[value] || value }
function statusType(value) { return { open: 'danger', acknowledged: 'warning', investigating: 'warning', action_planned: 'primary', in_progress: 'primary', resolved: 'success', closed: 'info' }[value] || 'info' }
function typeLabel(value) { return { data_quality: '数据质量', collection_exception: '采集异常', brand_risk: '品牌风险', operations_risk: '经营风险', opportunity: '招商机会', manual: '人工事项' }[value] || value }
function priorityLabel(value) { return { critical: '紧急', high: '高', normal: '普通', low: '低' }[value] || value }
function priorityType(value) { return { critical: 'danger', high: 'warning', normal: 'primary', low: 'info' }[value] || 'info' }
function feedbackLabel(value) { return { pending: '待反馈', valid: '有效', false_positive: '误报', no_action_required: '无需处理', data_problem: '数据问题' }[value] || value }
async function load() { loading.value = true; try { await scopeStore.load(); const result = await fetchCases({ status: status.value || undefined }); cases.value = result.items || [] } finally { loading.value = false } }
async function openDetail(row) { detail.value = await fetchCase(row.case_id); detailOpen.value = true }
async function advance(row) { try { const { value } = await ElMessageBox.prompt('填写处理日志；可记录负责人、结论或下一步。', '推进事项', { inputPlaceholder: '例如：已核对原始链接，等待补充门店主数据', confirmButtonText: '标记处理中', cancelButtonText: '取消' }); await updateCase(row.case_id, { status: 'in_progress', note: value || '' }); ElMessage.success('事项已更新'); await load() } catch {} }
async function createManual() { if (!form.title.trim()) { ElMessage.warning('请填写事项标题'); return } saving.value = true; try { await createCase({ ...form, source_type: 'manual', source_id: `manual:${Date.now()}`, scope_id: scopeStore.currentId || null }); ElMessage.success('事项已创建'); form.title = ''; form.description = ''; createOpen.value = false; await load() } finally { saving.value = false } }
watch(() => scopeStore.currentId, () => load().catch(() => {})); onMounted(load)
</script>

<style scoped>
.cases-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }.filter-control { width: 150px; }.evidence { max-height: 220px; overflow: auto; padding: 12px; border-radius: 8px; background: #f5f8fb; color: #42556a; font-size: 12px; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }.el-timeline p { margin: 4px 0 0; color: var(--bp-text-muted); font-size: 12px; } @media (max-width: 767px) { .filter-control { width: 100%; } }
</style>
