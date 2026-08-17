<template>
  <div class="change-password-page">
    <el-card class="change-password-card" shadow="always">
      <div class="page-title">修改密码</div>
      <p class="page-description">
        {{ userStore.user?.must_change_password ? '这是首次登录，请先设置仅你本人知晓的新密码。' : '修改密码后，所有已登录设备都需要重新登录。' }}
      </p>
      <el-alert v-if="userStore.user?.must_change_password" type="warning" :closable="false" show-icon title="临时密码不能继续用于系统操作。" />
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="password-form" @submit.prevent>
        <el-form-item label="当前密码" prop="currentPassword">
          <el-input v-model="form.currentPassword" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="form.newPassword" type="password" show-password autocomplete="new-password" />
          <div class="password-hint">至少 14 位，且至少包含大写字母、小写字母、数字、符号中的三类；不能包含用户名。</div>
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirmPassword">
          <el-input v-model="form.confirmPassword" type="password" show-password autocomplete="new-password" @keyup.enter="submit" />
        </el-form-item>
        <div class="actions">
          <el-button type="primary" :loading="saving" @click="submit">保存并重新登录</el-button>
          <el-button v-if="!userStore.user?.must_change_password" @click="router.replace('/')">取消</el-button>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()
const formRef = ref()
const saving = ref(false)
const form = reactive({ currentPassword: '', newPassword: '', confirmPassword: '' })
const rules = {
  currentPassword: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 14, message: '新密码至少需要 14 位', trigger: 'blur' },
  ],
  confirmPassword: [{
    validator: (_rule, value, callback) => callback(value === form.newPassword ? undefined : new Error('两次输入的新密码不一致')),
    trigger: 'blur',
  }],
}

async function submit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    await userStore.changePassword(form.currentPassword, form.newPassword)
    ElMessage.success('密码已更新，请使用新密码重新登录')
    router.replace('/login')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.change-password-page { height: 100%; display: flex; align-items: center; justify-content: center; padding: 16px; background: linear-gradient(135deg, #001529 0%, #0b2a4a 100%); }
.change-password-card { width: min(440px, 100%); border: 0; }
.page-title { font-size: 24px; font-weight: 700; color: #303133; }
.page-description { margin: 8px 0 16px; color: #606266; line-height: 1.6; }
.password-form { margin-top: 18px; }
.password-hint { margin-top: 6px; color: #909399; font-size: 12px; line-height: 1.5; }
.actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>
