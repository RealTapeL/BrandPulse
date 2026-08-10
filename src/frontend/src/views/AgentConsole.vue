<template>
  <div class="agent-console">
    <!-- 指令输入区 -->
    <el-card shadow="never" class="section">
      <template #header>Agent 控制台</template>
      <el-input
        v-model="prompt"
        type="textarea"
        :rows="3"
        placeholder="输入指令，如：统计苏州中心咖啡品牌的口碑分排名"
        aria-label="Agent 指令输入"
        @keydown.ctrl.enter="submit"
      />
      <el-input
        v-model="contextText"
        type="textarea"
        :rows="2"
        placeholder='上下文（JSON，可空），如：{"mall":"苏州中心","category":"咖啡"}'
        aria-label="Agent 上下文输入"
        class="context-input"
      />
      <div class="actions">
        <el-button
          type="primary"
          :loading="store.running"
          :disabled="!prompt.trim()"
          aria-label="执行 Agent 任务"
          @click="submit"
        >
          {{ store.running ? '执行中…' : '执行（Ctrl+Enter）' }}
        </el-button>
        <span v-if="store.running" class="hint">任务执行中，正在轮询状态…</span>
      </div>
      <el-alert v-if="contextError" type="error" :title="contextError" :closable="false" class="context-error" />
    </el-card>

    <!-- 当前任务 -->
    <el-card v-if="store.task" shadow="never" class="section">
      <template #header>
        <div class="task-head">
          <span>任务 {{ store.task.id }}</span>
          <el-tag :type="statusType(store.task.status)" size="small">{{ statusText(store.task.status) }}</el-tag>
        </div>
      </template>

      <div class="task-block">
        <div class="block-title">输入</div>
        <pre class="block-body">{{ store.task.input }}</pre>
      </div>

      <div class="task-block">
        <div class="block-title">执行日志</div>
        <el-timeline v-if="store.task.logs?.length" class="logs">
          <el-timeline-item v-for="(log, i) in store.task.logs" :key="i" :timestamp="log.time || ''">
            {{ log.message ?? log }}
          </el-timeline-item>
        </el-timeline>
        <el-text v-else type="info">暂无日志</el-text>
      </div>

      <div v-if="store.task.output" class="task-block">
        <div class="block-title">输出</div>
        <pre class="block-body output">{{ store.task.output }}</pre>
      </div>
      <el-alert v-if="store.task.error" type="error" :title="store.task.error" :closable="false" />
    </el-card>

    <!-- 错误态：retry -->
    <el-alert v-if="store.error" type="error" title="Agent 任务执行失败" :closable="false" class="section">
      <el-button size="small" aria-label="重试 Agent 任务" @click="submit">重试</el-button>
    </el-alert>

    <!-- 历史任务 -->
    <el-card v-if="store.history.length" shadow="never" class="section">
      <template #header>历史任务</template>
      <div class="table-scroll">
        <el-table :data="store.history" aria-label="历史任务列表">
        <el-table-column prop="id" label="任务 ID" width="160" />
        <el-table-column prop="input" label="指令" min-width="240" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup>
/**
 * Agent 控制台 /agent/console：发送指令 → POST /agent/execute 拿 task_id → 轮询任务状态展示日志与输出。
 * TODO: 后端就绪后，轮询可替换为 WebSocket / SSE 实时推送。
 */
import { onMounted, ref } from 'vue'
import { useAgentStore } from '../stores/agent'

const store = useAgentStore()
const prompt = ref('')
const contextText = ref('')
const contextError = ref('')

onMounted(() => {
  store.loadHistory().catch(() => {
    // 历史任务加载失败不影响新任务提交，统一由请求拦截器处理认证错误。
  })
})

function parseContext() {
  contextError.value = ''
  if (!contextText.value.trim()) return {}
  try {
    return JSON.parse(contextText.value)
  } catch {
    contextError.value = '上下文不是合法 JSON，请检查格式'
    return null
  }
}

async function submit() {
  const context = parseContext()
  if (context === null || !prompt.value.trim()) return
  await store.execute(prompt.value.trim(), context)
}

function statusType(s) {
  return { success: 'success', running: 'warning', pending: 'info', failed: 'danger' }[s] || 'info'
}

function statusText(s) {
  return { success: '成功', running: '运行中', pending: '排队中', failed: '失败' }[s] || s
}
</script>

<style scoped>
.agent-console {
  width: 100%;
  min-width: 0;
  max-width: var(--bp-content-max-width);
  margin: 0 auto;
  padding: var(--bp-space-4) var(--bp-space-5) 40px;
}
.section {
  margin-bottom: 16px;
}
.context-input {
  margin-top: 10px;
}
.context-error {
  margin-top: 10px;
}
.actions {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.hint {
  color: #909399;
  font-size: 12px;
}
.task-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.task-block {
  margin-bottom: 14px;
}
.block-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 6px;
}
.block-body {
  background: #f5f7fa;
  border-radius: 4px;
  padding: 10px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
}
.output {
  background: #f0f9eb;
}
.logs {
  padding-left: 4px;
}

@media (max-width: 767px) {
  .agent-console {
    padding: var(--bp-space-4) var(--bp-space-3) 28px;
  }

  .actions {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
