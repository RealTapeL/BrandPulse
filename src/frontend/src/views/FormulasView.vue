<template>
  <div class="page">
    <div class="page-header">
      <h2>指标公式管理</h2>
      <p class="desc">查看快照指标口径，并在选定的可信范围与数据快照上执行可追溯的自定义公式。</p>
    </div>

    <!-- 内置指标（只读） -->
    <h3 class="section-title">内置指标</h3>
    <el-row :gutter="16">
      <el-col v-for="m in builtinMetrics" :key="m.name" :xs="24" :md="12">
        <el-card shadow="never" class="metric-card">
          <div class="metric-head">
            <span class="metric-name">{{ m.name }}</span>
            <el-tag type="success" size="small" effect="light">启用中</el-tag>
          </div>
          <div class="formula-code">{{ m.formula }}</div>
          <div class="metric-block">
            <span class="metric-label">参数说明</span>
            <p class="metric-text">{{ m.params }}</p>
          </div>
          <div class="metric-block">
            <span class="metric-label">解读</span>
            <p class="metric-text">{{ m.meaning }}</p>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 自定义公式 -->
    <el-alert class="formula-note" type="info" :closable="false" show-icon title="自定义公式只读取所选范围的 valid 快照指标，并保存输入、公式定义和快照证据；结果仅作分析试验，不会自动写入机会判断、报告或招商结论。" />
    <div class="custom-head">
      <h3 class="section-title" style="margin: 0">自定义公式</h3>
      <div class="custom-actions">
        <el-select v-model="runScopeId" class="run-scope-select" placeholder="选择计算范围">
          <el-option v-for="scope in scopes" :key="scope.scope_id" :label="scopeLabel(scope)" :value="scope.scope_id" />
        </el-select>
        <el-button v-if="canManage" type="primary" :icon="'Plus'" @click="openCreate">新建公式</el-button>
      </div>
    </div>
    <el-card shadow="never" v-loading="loading">
      <div class="table-scroll">
        <el-table :data="formulas" border stripe empty-text="暂无自定义公式，点击右上角「新建公式」创建">
        <el-table-column prop="name" label="公式名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '-' }}</template>
        </el-table-column>
        <el-table-column label="表达式" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="expr-code">{{ row.expression }}</code>
          </template>
        </el-table-column>
        <el-table-column label="参数" min-width="160">
          <template #default="{ row }">
            <template v-if="row.params && row.params.length">
              <el-tag
                v-for="p in row.params"
                :key="p.key"
                size="small"
                type="info"
                effect="plain"
                class="param-tag"
              >
                {{ p.key }}={{ p.value }}
              </el-tag>
            </template>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              :loading="row._toggling"
              :disabled="!canManage"
              @change="(val) => toggleEnabled(row, val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="canManage" label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" :loading="row._running" :disabled="!runScopeId" @click="runNow(row)">按范围计算</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 新建 / 编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑公式' : '新建公式'"
      width="min(620px, calc(100vw - 32px))"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="公式名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：点评单店平均评价数" maxlength="50" show-word-limit />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" placeholder="公式的业务含义与用途" maxlength="200" />
        </el-form-item>
        <el-form-item label="表达式" prop="expression">
          <el-input
            v-model="form.expression"
            type="textarea"
            :rows="3"
            placeholder="例如：dp_review_count_stock / max(dp_store_count_observed, 1)"
          />
        </el-form-item>
        <el-form-item label="参数定义">
          <div class="params-editor">
            <div v-for="(p, i) in form.params" :key="i" class="param-row">
              <el-input v-model="p.key" class="param-input" placeholder="参数名，如 m" />
              <span class="param-eq">=</span>
              <el-input v-model="p.value" class="param-input" placeholder="默认值，如 300" />
              <el-button link type="danger" :icon="'Delete'" @click="form.params.splice(i, 1)" />
            </div>
            <el-button link type="primary" :icon="'Plus'" @click="form.params.push({ key: '', value: '' })">
              添加参数
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="备注信息（可选）" maxlength="200" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listFormulas,
  createFormula,
  updateFormula,
  deleteFormula,
  runFormula,
  validateExpression,
} from '../api/formulas'
import { fetchMonitoringScopes } from '../api/monitoring'
import { usePermissions } from '../composables/usePermissions'

const { can } = usePermissions()
const canManage = can('formula.manage')

// ---- 内置指标：与 metric_definitions / snapshot_metrics 保持一致，只读展示。 ----
const builtinMetrics = [
  {
    name: '点评累计评价数（公开存量）',
    formula: 'Σ review_count（当前 scope 快照内通过校验的点评门店）',
    params: '范围固定为 城市 × 商场 × 品类；只统计当前快照 accepted 的点评观测。',
    meaning: '反映公开评价存量，不代表近期热度、销售额或市场份额。',
  },
  {
    name: '点评评价份额',
    formula: '门店 review_count ÷ 同一 scope 的 Σ review_count',
    params: '仅比较当前快照内同一范围的点评门店；分子、分母和来源 URL 写入指标证据。',
    meaning: '用于观察同范围内公开评价分布，不等同真实市场份额或销售占比。',
  },
  {
    name: '贝叶斯加权口碑',
    formula: 'WR = (v/(v+m))·R + (m/(v+m))·C',
    params: 'R = 门店评分；v = 评价数；C/m 优先取同商场同品类比较池，样本不足时按证据记录的降级策略处理。',
    meaning: '仅在比较池满足最小样本时输出；未满足时标记 insufficient_sample，不强行给分。',
  },
  {
    name: '来源与实体映射覆盖率',
    formula: '成功来源数 ÷ 预期来源数；已确认映射观测数 ÷ 可用原始观测数',
    params: 'empty_validated / failed 不计为来源成功；未确认映射不进入品牌结论。',
    meaning: '先判断数据是否足以使用，再讨论机会或风险；低覆盖率会产生数据质量事项而非业务结论。',
  },
  {
    name: '点评评价趋势',
    formula: '当前累计评价数 − 前一可比快照累计评价数',
    params: '仅当来源完整、时间有序且累计数未下降时输出增量与增长率。',
    meaning: '不满足可比条件时不输出趋势结论，避免把采集缺失或累计回落伪装成业务变化。',
  },
]

// ---- 自定义公式 ----
const formulas = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const scopes = ref([])
const runScopeId = ref('')

const emptyForm = () => ({
  name: '',
  description: '',
  expression: '',
  params: [],
  enabled: true,
  remark: '',
})
const form = reactive(emptyForm())

const rules = {
  name: [{ required: true, message: '请输入公式名称', trigger: 'blur' }],
  expression: [
    { required: true, message: '请输入表达式', trigger: 'blur' },
    {
      validator: (rule, value, cb) => {
        const err = validateExpression(value)
        cb(err ? new Error(err) : undefined)
      },
      trigger: 'blur',
    },
  ],
}

async function load() {
  loading.value = true
  try {
    formulas.value = await listFormulas()
  } finally {
    loading.value = false
  }
}

function scopeLabel(scope) {
  return `${scope.city || '-'} · ${scope.mall_name || '-'} · ${scope.category || '-'}`
}

async function loadScopes() {
  const result = await fetchMonitoringScopes()
  scopes.value = result.items || []
  if (!runScopeId.value && scopes.value.length) runScopeId.value = scopes.value[0].scope_id
}

function resetForm(data) {
  Object.assign(form, emptyForm(), data || {})
  form.params = (data?.params || []).map((p) => ({ ...p }))
}

function openCreate() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  resetForm(row)
  dialogVisible.value = true
}

async function save() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  // 参数行校验：非空行必须 key/value 齐全
  const params = form.params.filter((p) => p.key.trim() || p.value.trim())
  for (const p of params) {
    if (!p.key.trim() || !p.value.trim()) {
      ElMessage.warning('参数定义不完整：参数名和默认值都要填写')
      return
    }
  }
  const payload = {
    name: form.name.trim(),
    description: form.description.trim(),
    expression: form.expression.trim(),
    params: params.map((p) => ({ key: p.key.trim(), value: p.value.trim() })),
    enabled: form.enabled,
    remark: form.remark.trim(),
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateFormula(editingId.value, payload)
      ElMessage.success('公式已更新')
    } else {
      await createFormula(payload)
      ElMessage.success('公式已创建')
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(`保存失败：${e.message || e}`)
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(row, val) {
  row._toggling = true
  try {
    await updateFormula(row.id, { enabled: val })
    row.enabled = val
    ElMessage.success(val ? `已启用「${row.name}」` : `已停用「${row.name}」`)
  } catch (e) {
    ElMessage.error(`操作失败：${e.message || e}`)
  } finally {
    row._toggling = false
  }
}

async function runNow(row) {
  if (!runScopeId.value) {
    ElMessage.warning('请先选择可信监测范围')
    return
  }
  row._running = true
  try {
    const result = await runFormula(row.id, { scopeId: runScopeId.value })
    const suffix = result.skipped ? `，${result.skipped} 条因输入不足跳过` : ''
    ElMessage.success(`已按快照 ${result.snapshot_id} 完成 ${result.saved} 条计算${suffix}`)
  } catch (e) {
    ElMessage.error(`计算失败：${e.response?.data?.detail || e.message || e}`)
  } finally {
    row._running = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除公式「${row.name}」吗？该操作不可恢复。`, '删除公式', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteFormula(row.id)
    ElMessage.success('公式已删除')
    await load()
  } catch (e) {
    ElMessage.error(`删除失败：${e.message || e}`)
  }
}

onMounted(async () => { await Promise.all([load(), loadScopes()]) })
</script>

<style scoped>
.metric-card {
  margin-bottom: 16px;
}
.metric-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.metric-name {
  font-size: 15px;
  font-weight: 600;
}
.metric-block {
  margin-top: 10px;
}
.metric-label {
  font-size: 12px;
  color: #909399;
}
.metric-text {
  margin: 2px 0 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

.custom-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 24px 0 12px;
}
.custom-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.run-scope-select { width: min(300px, 48vw); }
.formula-note { margin: 24px 0 12px; }

.expr-code {
  font-family: Consolas, Menlo, monospace;
  font-size: 12.5px;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 4px;
}
.param-tag {
  margin: 2px 4px 2px 0;
}

.params-editor {
  width: 100%;
}
.param-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.param-input {
  width: 160px;
}
.param-eq {
  color: #909399;
}

@media (max-width: 767px) {
  .custom-head {
    align-items: flex-start;
    gap: 12px;
    flex-wrap: wrap;
  }

  .custom-actions,
  .run-scope-select {
    width: 100%;
  }

  .param-row {
    flex-wrap: wrap;
  }

  .param-input {
    flex: 1 1 140px;
    width: auto;
  }
}
</style>
