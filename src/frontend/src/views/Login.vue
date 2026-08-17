<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="login-header">
        <div class="login-title">BrandPulse</div>
        <div class="login-sub">招商品牌情报平台 · 管理台</div>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            aria-label="用户名"
            placeholder="请输入用户名"
            autocomplete="username"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            aria-label="密码"
            placeholder="请输入密码"
            show-password
            autocomplete="current-password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          class="login-btn"
          type="primary"
          :loading="loading"
          aria-label="登录"
          @click="submit"
        >
          登 录
        </el-button>
      </el-form>
      <div class="login-tip">使用管理员分配的账号登录。首次使用临时密码时，系统会要求立即修改密码。</div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await userStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    // 支持 ?redirect= 回跳（路由守卫拦截时带上）
    router.replace(route.query.redirect || '/')
  } catch {
    // 错误提示由 axios 拦截器统一弹出，这里只复位加载态
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #001529 0%, #0b2a4a 100%);
}
.login-card {
  width: min(380px, calc(100% - 32px));
  border: none;
}
.login-header {
  text-align: center;
  margin-bottom: 20px;
}
.login-title {
  font-size: 24px;
  font-weight: 700;
}
.login-sub {
  color: #909399;
  font-size: 12px;
  margin-top: 6px;
}
.login-btn {
  width: 100%;
  margin-top: 8px;
}
.login-tip {
  margin-top: 14px;
  text-align: center;
  color: #c0c4cc;
  font-size: 12px;
}
</style>
