/**
 * e2e：登录 -> 打开 /brands -> 搜索 -> 点击进入详情。
 * 前置：npm run dev 已启动（mock 模式下任意账号密码可登录）。
 */
describe('品牌浏览路径', () => {
  it('登录 -> 品牌列表 -> 搜索 -> 进入详情', () => {
    // 1. 登录
    cy.visit('/#/login')
    cy.get('input[aria-label="用户名"]').type('admin')
    cy.get('input[aria-label="密码"]').type('123456')
    cy.get('button[aria-label="登录"]').click()
    cy.hash().should('eq', '#/')

    // 2. 打开品牌列表（第一页 10 条，总数 23）
    cy.visit('/#/brands')
    cy.get('.el-table__row', { timeout: 10000 }).should('have.length', 10)
    cy.contains('共 23 条')

    // 3. 搜索「瑞幸」
    cy.get('input[aria-label="搜索品牌名"]').type('瑞幸{enter}')
    cy.get('.el-table__row').should('have.length', 2)

    // 4. 点击进入详情
    cy.get('.el-table__row').first().click()
    cy.hash().should('match', /#\/brands\/\d+/)
    cy.contains('热度指数趋势', { timeout: 10000 })
    cy.contains('最近采集')
  })
})
