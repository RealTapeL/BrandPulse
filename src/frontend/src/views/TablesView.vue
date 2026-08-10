<template>
  <div class="page tables-page">
    <div class="page-header">
      <h2>数据表查看</h2>
      <p class="desc">浏览底层业务数据表，支持筛选、排序与分页</p>
    </div>

    <div class="tables-body">
      <!-- 左侧表选择 -->
      <el-card shadow="never" class="table-picker">
        <div
          v-for="t in TABLES"
          :key="t.name"
          class="table-item"
          :class="{ active: t.name === currentTable }"
          @click="switchTable(t.name)"
        >
          <el-icon><Coin /></el-icon>
          <div class="table-item-text">
            <span class="table-item-label">{{ t.label }}</span>
            <span class="table-item-name">{{ t.name }}</span>
          </div>
        </div>
      </el-card>

      <!-- 右侧数据区 -->
      <el-card shadow="never" class="table-content">
        <div class="toolbar">
          <div class="toolbar-info">
            <span class="toolbar-title">{{ conf.label }}</span>
            <span class="toolbar-desc">{{ conf.desc }}</span>
          </div>
          <div class="toolbar-actions">
            <el-input
              v-model="keywordInput"
              class="keyword-input"
              placeholder="关键字筛选（回车生效）"
              clearable
              @keyup.enter="applyKeyword"
              @clear="applyKeyword"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-button :icon="'Refresh'" :loading="loading" @click="load">刷新</el-button>
            <el-upload
              v-if="currentTable === 'store_operations'"
              :show-file-list="false"
              accept=".xlsx,.xlsm"
              :before-upload="handleOperationsUpload"
            >
              <el-button type="primary" :loading="uploading" :icon="'Upload'">导入经营 Excel</el-button>
            </el-upload>
          </div>
        </div>

        <!-- 错误态 -->
        <el-result v-if="error" icon="error" title="数据加载失败" :sub-title="error">
          <template #extra>
            <el-button type="primary" @click="load">重新加载</el-button>
          </template>
        </el-result>

        <template v-else>
          <div class="table-scroll">
            <el-table
              v-loading="loading"
              :data="rows"
              border
              stripe
              height="460"
              :empty-text="keyword ? '没有匹配关键字的记录' : '该表暂无数据'"
              @sort-change="onSortChange"
            >
              <el-table-column
                v-for="col in conf.columns"
                :key="col.prop"
                :prop="col.prop"
                :label="col.label"
                :sortable="col.sortable ? 'custom' : false"
                :width="col.width"
                :min-width="col.minWidth"
                show-overflow-tooltip
              >
                <template #default="{ row }">{{ formatCell(row[col.prop], col.prop) }}</template>
              </el-table-column>
            </el-table>
          </div>

          <div class="pager">
            <el-pagination
              v-model:current-page="page"
              v-model:page-size="size"
              :total="total"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next, jumper"
              background
              @current-change="load"
              @size-change="onSizeChange"
            />
          </div>
        </template>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { TABLES, getTableConfig, fetchTableData } from '../api/tables'
import { previewOperations, importOperations } from '../api/operations'

const currentTable = ref(TABLES[0].name)
const conf = computed(() => getTableConfig(currentTable.value))

const rows = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const keyword = ref('')
const keywordInput = ref('')
const sortProp = ref('')
const sortOrder = ref('')
const loading = ref(false)
const error = ref('')
const uploading = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetchTableData(currentTable.value, {
      page: page.value,
      size: size.value,
      keyword: keyword.value,
      sortProp: sortProp.value,
      sortOrder: sortOrder.value,
    })
    rows.value = resp.rows
    total.value = resp.total
  } catch (e) {
    error.value = String(e.message || e)
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function switchTable(name) {
  if (name === currentTable.value) return
  currentTable.value = name
  page.value = 1
  keyword.value = ''
  keywordInput.value = ''
  sortProp.value = ''
  sortOrder.value = ''
  load()
}

function applyKeyword() {
  keyword.value = keywordInput.value
  page.value = 1
  load()
}

function onSizeChange() {
  page.value = 1
  load()
}

function onSortChange({ prop, order }) {
  sortProp.value = order ? prop : ''
  sortOrder.value = order || ''
  page.value = 1
  load()
}

async function handleOperationsUpload(file) {
  uploading.value = true
  try {
    const preview = await previewOperations(file)
    if (preview.errors?.length) {
      const first = preview.errors.slice(0, 5).map((item) => `${item.row || item.record_id || '-'}: ${item.error}`).join('\n')
      ElMessage.error(`文件校验失败，未导入任何数据：\n${first}`)
      return false
    }
    await ElMessageBox.confirm(
      `已校验 ${preview.valid} 条真实经营记录，确认写入数据库？重复 record_id 将更新原记录。`,
      '确认导入',
      { type: 'warning', confirmButtonText: '确认导入', cancelButtonText: '取消' },
    )
    const result = await importOperations(file)
    ElMessage.success(`已导入 ${result.saved} 条经营记录`)
    await load()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(e.response?.data?.detail?.message || e.message || '经营数据导入失败')
    }
  } finally {
    uploading.value = false
  }
  return false
}

function formatCell(v, prop) {
  if (v == null || v === '') return '-'
  if (prop === 'sov' && Number.isFinite(Number(v))) return `${(Number(v) * 100).toFixed(1)}%`
  return v
}

onMounted(load)
</script>

<style scoped>
.tables-body {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 16px;
  align-items: start;
  min-width: 0;
}

.table-picker :deep(.el-card__body) {
  padding: 8px;
}
.table-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  color: #606266;
}
.table-item:hover {
  background: #f5f7fa;
}
.table-item.active {
  background: #ecf5ff;
  color: #409eff;
}
.table-item-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.table-item-label {
  font-size: 14px;
  font-weight: 600;
}
.table-item-name {
  font-size: 11px;
  color: #909399;
  font-family: Consolas, Menlo, monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}
.toolbar-title {
  font-size: 15px;
  font-weight: 600;
  margin-right: 10px;
}
.toolbar-desc {
  color: #909399;
  font-size: 12px;
}
.toolbar-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.keyword-input {
  width: 260px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

@media (max-width: 900px) {
  .tables-body {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 767px) {
  .keyword-input {
    width: 100%;
  }

  .toolbar-actions {
    width: 100%;
  }

  .toolbar-actions > .el-button,
  .toolbar-actions :deep(.el-upload) {
    flex: 1 1 auto;
  }

  .pager {
    justify-content: flex-start;
    overflow-x: auto;
    padding-bottom: 2px;
  }
}
</style>
