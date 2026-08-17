<template>
  <el-drawer
    :model-value="modelValue"
    title="询问 BrandPulse"
    direction="rtl"
    size="min(480px, 100vw)"
    class="assistant-drawer"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="assistant-context">
      <el-icon><Location /></el-icon>
      <span>当前范围：{{ scopeStore.label }}</span>
    </div>
    <p class="assistant-note">基于已接入的业务数据与工具回答；数据未就绪时会明确说明。</p>

    <div ref="messageList" class="assistant-messages">
      <div v-if="!messages.length" class="assistant-welcome">
        <el-icon :size="34"><ChatLineRound /></el-icon>
        <strong>从一个业务问题开始</strong>
        <p>助手会结合当前监测范围查询已接入的数据。</p>
        <button v-for="question in examples" :key="question" class="prompt-chip" type="button" @click="ask(question)">{{ question }}</button>
      </div>
      <template v-for="(message, index) in messages" :key="`${message.time}-${index}`">
        <div class="assistant-message" :class="message.role">
          <div class="assistant-message__role">{{ message.role === 'user' ? '你' : 'BrandPulse' }}</div>
          <div class="assistant-message__content">
            <MarkdownText v-if="message.role === 'assistant'" :text="message.content" />
            <span v-else>{{ message.content }}</span>
          </div>
        </div>
      </template>
      <div v-if="sending" class="assistant-message assistant"><div class="assistant-message__role">BrandPulse</div><div class="assistant-message__content">正在查询已接入的数据…</div></div>
    </div>

    <div class="assistant-composer">
      <el-input v-model="input" type="textarea" resize="none" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="例如：找出口碑高但声量偏低的品牌" :disabled="sending" @keydown="onKeydown" />
      <div class="assistant-composer__actions">
        <el-button text :disabled="!messages.length || sending" @click="clear">清空</el-button>
        <el-button type="primary" :loading="sending" :disabled="!input.trim()" @click="ask(input)">发送</el-button>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { nextTick, ref } from 'vue'
import MarkdownText from './MarkdownText.vue'
import { sendChat } from '../api/chat'
import { useScopeStore } from '../stores/scope'

defineProps({ modelValue: { type: Boolean, default: false } })
defineEmits(['update:modelValue'])

const scopeStore = useScopeStore()
const messages = ref([])
const input = ref('')
const sending = ref(false)
const messageList = ref(null)
const examples = [
  '找出口碑高但声量偏低的品牌',
  '当前范围有哪些数据问题影响招商判断？',
  '当前快照中哪些公开竞争线索需要人工核实？',
]

async function scrollToBottom() {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}
function onKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    ask(input.value)
  }
}
async function ask(value) {
  const question = String(value || '').trim()
  if (!question || sending.value) return
  messages.value.push({ role: 'user', content: question, time: Date.now() })
  input.value = ''
  sending.value = true
  await scrollToBottom()
  const history = messages.value.slice(-10).map(({ role, content }) => ({ role, content }))
  try {
    const result = await sendChat(question, history, scopeStore.currentId)
    messages.value.push({ role: 'assistant', content: formatAnswer(result), time: Date.now() })
  } catch (error) {
    messages.value.push({ role: 'assistant', content: `当前无法完成查询：${error.response?.data?.detail || error.message || '未知错误'}`, time: Date.now() })
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}
function clear() { messages.value = [] }
function formatAnswer(result) {
  const answer = result.answer || '服务未返回可展示的内容。'
  const evidence = result.evidence || {}
  if (evidence.status === 'scope_not_selected') return `${answer}\n\n---\n**数据上下文**：当前未选择监测范围，不能将回答视为特定项目的可信结论。`
  if (evidence.status === 'unavailable') return `${answer}\n\n---\n**数据上下文**：${evidence.message || '当前范围未取得可信快照。'}`
  const snapshot = evidence.snapshot || {}
  const scope = evidence.scope || {}
  return `${answer}\n\n---\n**当前范围证据**：${scope.city || '-'} · ${scope.mall_name || '-'} · ${scope.category || '-'}；快照 \`${snapshot.snapshot_id || '-'}\`；截止 ${snapshot.observed_at || '-'}；质量 ${snapshot.quality_grade || '-'}；来源覆盖 ${JSON.stringify(snapshot.source_coverage || {})}。`
}
</script>

<style scoped>
.assistant-context { display: flex; align-items: center; gap: 7px; width: fit-content; padding: 6px 9px; border-radius: 7px; background: #edf5ff; color: #2869bd; font-size: 12px; }
.assistant-note { margin: 10px 0 14px; color: var(--bp-text-muted); font-size: 12px; line-height: 1.55; }
.assistant-messages { height: calc(100vh - 250px); min-height: 340px; overflow: auto; padding: 0 2px 16px; }
.assistant-welcome { display: flex; align-items: flex-start; flex-direction: column; padding: 34px 10px; color: var(--bp-text-muted); }
.assistant-welcome > .el-icon { margin-bottom: 10px; color: var(--bp-primary); }
.assistant-welcome strong { color: var(--bp-text-strong); font-size: 16px; }
.assistant-welcome p { margin: 7px 0 14px; font-size: 12px; }
.prompt-chip { width: 100%; margin-top: 7px; padding: 10px 12px; border: 1px solid #dce8f7; border-radius: 8px; background: #fff; color: #35506f; cursor: pointer; font: inherit; font-size: 13px; line-height: 1.45; text-align: left; }
.prompt-chip:hover { border-color: #8db8ed; background: #f6faff; color: var(--bp-primary); }
.assistant-message { margin: 14px 0; }
.assistant-message__role { margin-bottom: 5px; color: var(--bp-text-muted); font-size: 11px; font-weight: 700; }
.assistant-message__content { max-width: 92%; padding: 10px 12px; border-radius: 9px; background: #f4f7fb; color: var(--bp-text-primary); font-size: 13px; line-height: 1.65; }
.assistant-message.user { display: flex; align-items: flex-end; flex-direction: column; }
.assistant-message.user .assistant-message__content { background: #e8f1ff; color: #174b8e; }
.assistant-composer { border-top: 1px solid #e9eef4; padding-top: 12px; }
.assistant-composer__actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
</style>
