/**
 * Agent 接口（/api/v1/agent）：
 * executeAgent  发起任务（prompt + context）→ { task_id }
 * getTask       查询任务状态 → { id, status, input, output, logs }
 */
import api from './index'

export function executeAgent(prompt, context = {}) {
  return api.post('/v1/agent/execute', { prompt, context }).then((r) => r.data)
}

export function getTask(id) {
  return api.get(`/v1/agent/tasks/${id}`).then((r) => r.data)
}
