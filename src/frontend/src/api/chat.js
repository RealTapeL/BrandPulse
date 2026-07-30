import { request } from './http'

/**
 * 对话助手 API 契约（后端待实现，前端按此调用，失败优雅降级）：
 *   POST /api/chat
 *   body: { question: string, history: [{ role: 'user'|'assistant', content: string }] }
 *   返回: { answer: string }
 */
export function sendChat(question, history) {
  return request('/api/chat', {
    method: 'POST',
    body: { question, history },
    timeout: 30000,
    silent: true, // 失败由聊天页降级为系统提示消息，不弹全局错误
  })
}
