<template>
  <div class="page users-page">
    <div class="page-header">
      <div>
        <h2>账号与权限</h2>
        <p class="desc">账号、角色和临时密码均由管理员管理；权限在后端实时校验。</p>
      </div>
      <el-button type="primary" :icon="'Plus'" @click="createVisible = true">新增账号</el-button>
    </div>

    <el-alert type="info" :closable="false" show-icon class="role-summary">
      <template #title>管理员可管理账号、审计和系统配置；运营人员可执行采集、指标、导入、预测及报告；只读人员只能查看业务数据并使用只读 Agent。</template>
    </el-alert>

    <el-card shadow="never">
      <template #header><div class="section-title"><span>用户列表</span><el-button size="small" :loading="loading" @click="load">刷新</el-button></div></template>
      <div class="table-scroll">
        <el-table :data="users" border stripe empty-text="暂无账号">
          <el-table-column prop="username" label="用户名" min-width="160" />
          <el-table-column label="角色" width="140">
            <template #default="{ row }">
              <el-select :model-value="row.role" size="small" :disabled="row.id === userStore.user?.id" @change="(role) => saveUser(row, { role })">
                <el-option label="管理员" value="admin" />
                <el-option label="运营人员" value="operator" />
                <el-option label="只读人员" value="viewer" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }"><el-switch :model-value="row.is_active" :disabled="row.id === userStore.user?.id" @change="(is_active) => saveUser(row, { is_active })" /></template>
          </el-table-column>
          <el-table-column label="密码状态" width="130"><template #default="{ row }"><el-tag :type="row.must_change_password ? 'warning' : 'success'">{{ row.must_change_password ? '待修改临时密码' : '已设置' }}</el-tag></template></el-table-column>
          <el-table-column prop="last_login_at" label="最近登录" min-width="180"><template #default="{ row }">{{ row.last_login_at || '从未登录' }}</template></el-table-column>
          <el-table-column label="操作" width="130" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="resetPassword(row)">重置密码</el-button></template></el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-dialog v-model="createVisible" title="新增账号" width="min(480px, calc(100% - 32px))" @closed="resetCreateForm">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-position="top" @submit.prevent>
        <el-form-item label="用户名" prop="username"><el-input v-model="createForm.username" autocomplete="off" /></el-form-item>
        <el-form-item label="角色" prop="role"><el-select v-model="createForm.role" class="full-width"><el-option label="管理员" value="admin" /><el-option label="运营人员" value="operator" /><el-option label="只读人员" value="viewer" /></el-select></el-form-item>
        <el-form-item label="临时密码（可选）" prop="temporary_password"><el-input v-model="createForm.temporary_password" type="password" show-password autocomplete="new-password" placeholder="留空则由系统生成一次性临时密码" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="createVisible = false">取消</el-button><el-button type="primary" :loading="creating" @click="create">创建账号</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createUser, fetchUsers, resetUserPassword, updateUser } from '../api/users'
import { useUserStore } from '../stores/user'

const userStore = useUserStore()
const users = ref([])
const loading = ref(false)
const createVisible = ref(false)
const creating = ref(false)
const createFormRef = ref()
const createForm = reactive({ username: '', role: 'viewer', temporary_password: '' })
const createRules = {
  username: [{ required: true, message: '请输入 3-64 位用户名', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

async function load() {
  loading.value = true
  try { users.value = (await fetchUsers()).items || [] } finally { loading.value = false }
}
async function saveUser(row, payload) {
  await updateUser(row.id, payload)
  ElMessage.success('账号设置已保存，相关会话已失效')
  await load()
}
function resetCreateForm() {
  createForm.username = ''; createForm.role = 'viewer'; createForm.temporary_password = ''
  createFormRef.value?.clearValidate()
}
async function create() {
  const valid = await createFormRef.value.validate().catch(() => false)
  if (!valid) return
  creating.value = true
  try {
    const result = await createUser({ ...createForm, temporary_password: createForm.temporary_password || undefined })
    createVisible.value = false
    await ElMessageBox.alert(`请仅通过受控渠道交付给用户：${result.temporary_password}`, `账号 ${result.user.username} 已创建`, {
      confirmButtonText: '我已安全保存临时密码',
      type: 'warning',
      closeOnClickModal: false,
    })
    await load()
  } finally { creating.value = false }
}
async function resetPassword(row) {
  try {
    await ElMessageBox.confirm(`重置“${row.username}”的密码会注销其所有已登录会话，是否继续？`, '确认重置密码', { type: 'warning' })
  } catch {
    return
  }
  const result = await resetUserPassword(row.id)
  await ElMessageBox.alert(`请仅通过受控渠道交付给用户：${result.temporary_password}`, `已重置 ${row.username} 的临时密码`, {
    confirmButtonText: '我已安全保存临时密码',
    type: 'warning',
    closeOnClickModal: false,
  })
  await load()
}

onMounted(load)
</script>

<style scoped>
.users-page { max-width: var(--bp-content-max-width); margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; }
.desc { margin: 6px 0 0; color: #606266; }
.role-summary { margin-bottom: 16px; }
.section-title { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-weight: 600; }
.full-width { width: 100%; }
@media (max-width: 767px) { .page-header { flex-direction: column; } }
</style>
