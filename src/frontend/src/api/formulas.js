/**
 * 自定义指标公式 API。
 *
 * 后端契约（待实现）：
 *   GET    /api/formulas          -> { formulas: [...] }
 *   POST   /api/formulas          body: Formula -> Formula（含 id）
 *   PUT    /api/formulas/{id}     body: Formula -> Formula
 *   DELETE /api/formulas/{id}     -> { ok: true }
 *
 * Formula: { id, name, description, expression, params: [{key, value}],
 *            enabled: boolean, remark, created_at, updated_at }
 *
 * 当前实现：localStorage 持久化（带版本号 key）。
 * 后端接口上线后，把 USE_BACKEND_FORMULA_API 置为 true 即可（一行切换）。
 */
import { request } from './http'

const USE_BACKEND_FORMULA_API = false
const STORAGE_KEY = 'brandpulse.custom-formulas.v1'

function loadAll() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

function saveAll(list) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
}

function genId() {
  return `f_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

export async function listFormulas() {
  if (USE_BACKEND_FORMULA_API) {
    const resp = await request('/api/formulas')
    return resp.formulas || []
  }
  return loadAll()
}

export async function createFormula(formula) {
  if (USE_BACKEND_FORMULA_API) {
    return request('/api/formulas', { method: 'POST', body: formula })
  }
  const list = loadAll()
  const now = new Date().toISOString()
  const item = { ...formula, id: genId(), created_at: now, updated_at: now }
  list.push(item)
  saveAll(list)
  return item
}

export async function updateFormula(id, patch) {
  if (USE_BACKEND_FORMULA_API) {
    return request(`/api/formulas/${id}`, { method: 'PUT', body: patch })
  }
  const list = loadAll()
  const idx = list.findIndex((f) => f.id === id)
  if (idx === -1) throw new Error('公式不存在')
  list[idx] = { ...list[idx], ...patch, id, updated_at: new Date().toISOString() }
  saveAll(list)
  return list[idx]
}

export async function deleteFormula(id) {
  if (USE_BACKEND_FORMULA_API) {
    return request(`/api/formulas/${id}`, { method: 'DELETE' })
  }
  saveAll(loadAll().filter((f) => f.id !== id))
}

/**
 * 表达式基础校验（前端防御，禁止明显危险内容）。
 * @returns {string} 空串表示通过，否则为错误提示
 */
export function validateExpression(expr) {
  const s = (expr || '').trim()
  if (!s) return '表达式不能为空'
  if (s.length > 500) return '表达式过长（最多 500 字符）'

  // 括号配对
  let depth = 0
  for (const ch of s) {
    if (ch === '(') depth += 1
    if (ch === ')') depth -= 1
    if (depth < 0) return '括号不匹配：出现多余的右括号'
  }
  if (depth !== 0) return '括号不匹配：存在未闭合的左括号'

  // 危险字符 / 关键字
  const forbidden = [/;/, /`/, /\bimport\b/i, /\brequire\b/i, /\beval\b/i, /\bFunction\b/, /\bwindow\b/i, /\bdocument\b/i, /\bfetch\b/i, /\bajax\b/i, /=>/, /\bwhile\b/i, /\bfor\b/i]
  for (const re of forbidden) {
    if (re.test(s)) return `表达式包含不允许的内容：${s.match(re)[0]}`
  }

  // 只允许数字、字母、下划线、运算符、括号、小数点、逗号、空格、百分号
  if (!/^[\w\s+\-*/%().,<>=!&|^~?:\u4e00-\u9fa5]+$/.test(s)) {
    return '表达式包含无法识别的字符，只允许变量名、数字和常见运算符'
  }
  return ''
}
