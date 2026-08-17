<template>
  <div class="chat-page">
    <div class="page-header chat-header">
      <div>
        <h2>对话助手</h2>
        <p class="desc">基于品牌情报数据的智能问答（会话保存在本地浏览器）</p>
      </div>
      <el-button :icon="'Delete'" :disabled="!messages.length || sending" @click="clearHistory">
        清空会话
      </el-button>
    </div>

    <el-card shadow="never" class="chat-card">
      <!-- 消息列表 -->
      <div ref="msgListEl" class="msg-list">
        <!-- 空态 -->
        <div v-if="!messages.length" class="chat-empty">
          <el-icon :size="44" color="#c0c4cc"><ChatLineRound /></el-icon>
          <p class="chat-empty-title">向 BrandPulse 助手提问</p>
          <p class="chat-empty-sub">试试这些示例问题：</p>
          <div class="examples">
            <el-tag
              v-for="q in examples"
              :key="q"
              class="example-tag"
              type="info"
              @click="useExample(q)"
            >
              {{ q }}
            </el-tag>
          </div>
        </div>

        <template v-for="(msg, i) in messages" :key="i">
          <!-- 系统提示消息（降级提示等） -->
          <div v-if="msg.role === 'system'" class="msg-system">
            <el-alert type="warning" :title="msg.content" :closable="false" show-icon />
          </div>

          <!-- 用户 / 助手气泡 -->
          <div v-else class="msg-row" :class="msg.role">
            <div class="avatar" :class="msg.role">
              <el-icon v-if="msg.role === 'assistant'"><Service /></el-icon>
              <el-icon v-else><User /></el-icon>
            </div>
            <div class="bubble" :class="msg.role">
              <MarkdownText v-if="msg.role === 'assistant'" :text="msg.content" />
              <span v-else class="plain-text">{{ msg.content }}</span>
              <div class="msg-time">{{ formatTime(msg.time) }}</div>
            </div>
          </div>
        </template>

        <!-- 发送中 -->
        <div v-if="sending" class="msg-row assistant">
          <div class="avatar assistant"><el-icon><Service /></el-icon></div>
          <div class="bubble assistant typing">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input-area">
        <el-input
          v-model="input"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 6 }"
          resize="none"
          placeholder="输入问题，Enter 发送，Shift+Enter 换行"
          :disabled="sending"
          @keydown="onKeydown"
        />
        <el-button
          type="primary"
          :icon="'Promotion'"
          :loading="sending"
          :disabled="!input.trim()"
          @click="send"
        >
          发送
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import MarkdownText from '../components/MarkdownText.vue'
import { sendChat } from '../api/chat'
import { useScopeStore } from '../stores/scope'

const STORAGE_KEY = 'brandpulse.chat-history.v1'
// 发送给后端的历史窗口（只含 user/assistant，不含系统提示）
const HISTORY_WINDOW = 10

const examples = [
  '苏州中心咖啡品类里口碑最好的门店是哪家？',
  '当前范围有哪些数据质量问题影响判断？',
  '当前快照有哪些待人工确认的机会信号？',
  '最近有什么高点赞的小红书笔记？',
]

const messages = ref([])
const input = ref('')
const sending = ref(false)
const msgListEl = ref(null)
const scopeStore = useScopeStore()

onMounted(() => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const list = raw ? JSON.parse(raw) : []
    if (Array.isArray(list)) messages.value = list
  } catch {
    // 本地历史损坏时静默重置
  }
})

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.value))
}

async function scrollToBottom() {
  await nextTick()
  const el = msgListEl.value
  if (el) el.scrollTop = el.scrollHeight
}

function useExample(q) {
  input.value = q
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

async function send() {
  const question = input.value.trim()
  if (!question || sending.value) return

  messages.value.push({ role: 'user', content: question, time: Date.now() })
  input.value = ''
  sending.value = true
  persist()
  await scrollToBottom()

  const history = messages.value
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .slice(-HISTORY_WINDOW)
    .map((m) => ({ role: m.role, content: m.content }))

  try {
    const resp = await sendChat(question, history, scopeStore.currentId)
    messages.value.push({ role: 'assistant', content: formatAnswer(resp), time: Date.now() })
  } catch (e) {
    messages.value.push({
      role: 'system',
      content: `对话服务暂不可用：${e.response?.data?.detail || e.message || '未知错误'}`,
      time: Date.now(),
    })
  } finally {
    sending.value = false
    persist()
    await scrollToBottom()
  }
}

async function clearHistory() {
  try {
    await ElMessageBox.confirm('确定清空当前会话历史吗？该操作不可恢复。', '清空会话', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  messages.value = []
  persist()
  ElMessage.success('会话已清空')
}

function formatTime(t) {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

function formatAnswer(result) {
  const answer = result.answer || '（服务未返回内容）'
  const evidence = result.evidence || {}
  if (evidence.status === 'scope_not_selected') return `${answer}\n\n---\n**数据上下文**：当前未选择监测范围，不能将回答视为特定项目的可信结论。`
  if (evidence.status === 'unavailable') return `${answer}\n\n---\n**数据上下文**：${evidence.message || '当前范围未取得可信快照。'}`
  const snapshot = evidence.snapshot || {}
  const scope = evidence.scope || {}
  return `${answer}\n\n---\n**当前范围证据**：${scope.city || '-'} · ${scope.mall_name || '-'} · ${scope.category || '-'}；快照 \`${snapshot.snapshot_id || '-'}\`；截止 ${snapshot.observed_at || '-'}；质量 ${snapshot.quality_grade || '-'}；来源覆盖 ${JSON.stringify(snapshot.source_coverage || {})}。`
}
</script>

<style scoped>
.chat-page {
  padding: var(--bp-space-4) var(--bp-space-5) 28px;
  max-width: 1000px;
  width: 100%;
  margin: 0 auto;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}
.chat-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}
.chat-card {
  flex: 1;
  min-height: 0;
  display: flex;
}
.chat-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 0;
  min-height: 0;
}

.msg-list {
  flex: 1;
  min-height: 320px;
  overflow-y: auto;
  padding: 20px;
}

.chat-empty {
  text-align: center;
  padding: 60px 0 40px;
  color: #909399;
}
.chat-empty-title {
  font-size: 16px;
  font-weight: 600;
  color: #606266;
  margin: 12px 0 4px;
}
.chat-empty-sub {
  font-size: 13px;
  margin: 0 0 12px;
}
.examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  max-width: 560px;
  margin: 0 auto;
}
.example-tag {
  cursor: pointer;
}
.example-tag:hover {
  color: #409eff;
  border-color: #409eff;
}

.msg-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: flex-start;
}
.msg-row.user {
  flex-direction: row-reverse;
}
.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #fff;
}
.avatar.assistant {
  background: #409eff;
}
.avatar.user {
  background: #67c23a;
}
.bubble {
  max-width: 75%;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  position: relative;
}
.bubble.assistant {
  background: #f4f4f5;
  border-top-left-radius: 2px;
}
.bubble.user {
  background: #409eff;
  color: #fff;
  border-top-right-radius: 2px;
}
.plain-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}
.msg-time {
  font-size: 11px;
  margin-top: 6px;
  opacity: 0.6;
}
.bubble.user .msg-time {
  text-align: right;
}

.msg-system {
  max-width: 520px;
  margin: 0 auto 16px;
}

.bubble.typing {
  display: flex;
  gap: 5px;
  align-items: center;
  padding: 14px 16px;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #909399;
  animation: blink 1.2s infinite;
}
.dot:nth-child(2) {
  animation-delay: 0.2s;
}
.dot:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes blink {
  0%, 80%, 100% { opacity: 0.25; }
  40% { opacity: 1; }
}

.input-area {
  display: flex;
  gap: 10px;
  padding: 14px 16px;
  border-top: 1px solid #e4e7ed;
  align-items: flex-end;
}

@media (max-width: 767px) {
  .chat-page {
    padding: var(--bp-space-4) var(--bp-space-3) 16px;
  }

  .chat-header {
    align-items: stretch;
  }

  .chat-header > .el-button {
    align-self: flex-end;
  }

  .msg-list {
    padding: 16px 12px;
  }

  .bubble {
    max-width: calc(100% - 44px);
  }

  .input-area {
    flex-direction: column;
    align-items: stretch;
    padding: 12px;
  }

  .input-area > .el-button {
    width: 100%;
  }
}
</style>
