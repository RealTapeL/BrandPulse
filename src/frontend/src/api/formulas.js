/**
 * 自定义指标公式 API。
 *
 * 后端契约：
 *   GET    /api/formulas          -> { formulas: [...] }
 *   POST   /api/formulas          body: Formula -> Formula（含 id）
 *   PUT    /api/formulas/{id}     body: Formula -> Formula
 *   DELETE /api/formulas/{id}     -> { ok: true }
 *
 * Formula: { id, name, description, expression, params: [{key, value}],
 *            enabled: boolean, remark, created_at, updated_at }
 *
 * 由 FastAPI + PostgreSQL 持久化；启用后由指标管道按品牌真实数据计算。
 */
import api from './index'

export async function listFormulas() {
  const { data } = await api.get('/v1/formulas')
  return data.formulas || []
}

export async function createFormula(formula) {
  const { data } = await api.post('/v1/formulas', formula)
  return data
}

export async function updateFormula(id, patch) {
  const { data } = await api.put(`/v1/formulas/${id}`, patch)
  return data
}

export async function deleteFormula(id) {
  await api.delete(`/v1/formulas/${id}`)
}

export async function runFormula(id, statDate) {
  const { data } = await api.post(`/v1/formulas/${id}/run`, null, {
    params: statDate ? { stat_date: statDate } : undefined,
  })
  return data
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
