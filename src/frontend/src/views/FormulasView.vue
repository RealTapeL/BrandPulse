<template>
  <div class="page">
    <div class="page-header">
      <h2>指标公式管理</h2>
      <p class="desc">查看内置指标口径，管理自定义计算公式</p>
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
    <div class="custom-head">
      <h3 class="section-title" style="margin: 0">自定义公式</h3>
      <el-button type="primary" :icon="'Plus'" @click="openCreate">新建公式</el-button>
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
              @change="(val) => toggleEnabled(row, val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" :loading="row._running" @click="runNow(row)">立即计算</el-button>
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
          <el-input v-model="form.name" placeholder="例如：热度指数（自定义权重）" maxlength="50" show-word-limit />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" placeholder="公式的业务含义与用途" maxlength="200" />
        </el-form-item>
        <el-form-item label="表达式" prop="expression">
          <el-input
            v-model="form.expression"
            type="textarea"
            :rows="3"
            placeholder="例如：100 * ln(1 + review_count)；变量来自真实指标和点评数据"
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

// ---- 内置指标（口径与后端 src/backend/brandpulse/indicators/ 保持一致，只读展示） ----
const builtinMetrics = [
  {
    name: '口碑分',
    formula: 'WR = (v/(v+m))·R + (m/(v+m))·C',
    params: 'R = 门店评分；v = 门店评价数；C = 当日全城加权平均评分；m = 当日全城门店评价数中位数（可信度阈值）',
    meaning: '贝叶斯加权（IMDB 同款算法）。评价数越少，评分越被拉回全城均值，避免「5 条评价的 5.0 分」虚高（0~5 分）',
  },
  {
    name: '热度指数',
    formula: 'heat = 100·ln(1+v) / ln(1+50000)',
    params: 'v = 点评评价数；50000 = 固定参考基准 REVIEW_REF（5 万评价视为满分热度）',
    meaning: '对数压缩长尾，固定基准归一保证指数跨天、跨商场可比（0~100）',
  },
  {
    name: 'SOV 声量份额',
    formula: 'SOV = 门店评价数 ÷ 同商场同品类当日总评价数',
    params: '评价数取点评 dp_shop_metrics 当日采集值；分母为同商场（苏州中心）咖啡品类全部门店评价数之和',
    meaning: '衡量门店在同商场同品类中的声量占比（0~1）。真实消费后的发声量，比裸评分更接近市场份额体感',
  },
  {
    name: '趋势（周环比动量）',
    formula: 'wow = (本期热度 − 上期热度) / 上期热度',
    params: '热度取热度指标产出的固定基准热度指数；波动率窗口 4 期（近 N 期热度标准差 ÷ 均值）',
    meaning: '数据积累不足 2 期时动量为 NULL，属正常状态。高动量 + 低波动 = 正在起势且非网红泡沫的品牌',
  },
]

// ---- 自定义公式 ----
const formulas = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref(null)

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
  row._running = true
  try {
    const result = await runFormula(row.id)
    ElMessage.success(`已按最新真实指标计算 ${result.saved} 条结果`)
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

onMounted(load)
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

  .param-row {
    flex-wrap: wrap;
  }

  .param-input {
    flex: 1 1 140px;
    width: auto;
  }
}
</style>
