/**
 * Pinia agent store：发起 Agent 任务并轮询状态。
 * 终态：success / failed；轮询间隔 2s，上限 60 次（2 分钟）后自动放弃。
 */
import { defineStore } from 'pinia'
import { executeAgent, getTask } from '../api/agent'

const POLL_INTERVAL = 2000
const MAX_POLLS = 60
const TERMINAL = ['success', 'failed']

export const useAgentStore = defineStore('agent', {
  state: () => ({
    task: null, // 当前任务 { id, status, input, output, logs }
    running: false,
    error: null,
    history: [], // 最近任务（演示期仅内存保存）
  }),
  actions: {
    async execute(prompt, context = {}) {
      this.error = null
      this.task = null
      this.running = true
      try {
        const { task_id } = await executeAgent(prompt, context)
        await this.poll(task_id)
      } catch (e) {
        this.error = e
      } finally {
        this.running = false
      }
    },
    async poll(taskId) {
      for (let i = 0; i < MAX_POLLS; i++) {
        const task = await getTask(taskId)
        this.task = task
        if (TERMINAL.includes(task.status)) {
          this.history.unshift(task)
          return task
        }
        await new Promise((r) => setTimeout(r, POLL_INTERVAL))
      }
      throw new Error('任务轮询超时')
    },
  },
})
