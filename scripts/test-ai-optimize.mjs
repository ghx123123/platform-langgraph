// test-ai-optimize.mjs — 用户视角端到端验证: 点 AI 优化 → 输入提示词 → 生成 → 确认无校验错误
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/cc/projects/multi_agent_platform_langgraph/frontend/')
const { chromium } = require('playwright-core')

const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)) })
page.on('response', (r) => { if (r.status() >= 400) errs.push(`${r.status()} ${r.url().slice(-90)}`) })

await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2500)

// 点击 python资料单元
const unitOpen = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => x.innerText && x.innerText.includes('python资料单元'))
  if (b) { b.click(); return true }
  return false
})
console.log('unitOpen:', unitOpen)
await page.waitForTimeout(2500)

// 点击 AI 优化
const aiClick = await page.evaluate(() => {
  const t = document.querySelector('button')
  const b = [...document.querySelectorAll('button')].find((x) => x.innerText && x.innerText.trim().startsWith('AI 优化'))
  if (b) { b.click(); return true }
  return false
})
console.log('aiClick:', aiClick, '| errs so far:', errs.length)
await page.waitForTimeout(800)

// 检查优化面板是否出现并输入提示词
const panelInfo = await page.evaluate(() => {
  const ta = document.querySelector('textarea')
  const hasPanel = !!(ta && document.body.innerText.includes('AI 优化'))
  return { hasPanel, hasTextarea: !!ta }
})
console.log('panelInfo:', JSON.stringify(panelInfo))

// 输入提示词并触发生成
const sentInfo = await page.evaluate(() => {
  const panel = document.querySelector('.refine-panel')
  if (!panel) return { ok: false, reason: 'no panel' }
  const ta = panel.querySelector('textarea')
  if (!ta) return { ok: false, reason: 'no textarea' }
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
  setter.call(ta, '增加重难点解释，扩充知识点的详细说明')
  ta.dispatchEvent(new Event('input', { bubbles: true }))
  const b = [...panel.querySelectorAll('button')].find((x) => x.innerText && x.innerText.includes('生成优化版本'))
  if (b) { b.click(); return { ok: true, btnText: b.innerText.slice(0, 30) } }
  return { ok: false, reason: 'no submit btn', btns: [...panel.querySelectorAll('button')].map((x) => x.innerText.slice(0, 20)) }
})
console.log('sentInfo:', JSON.stringify(sentInfo))
await page.waitForTimeout(12000) // 等 LLM 生成 + 保存

const final = await page.evaluate(() => {
  const t = document.body.innerText || ''
  return {
    hasNotice: t.includes('优化版本') || t.includes('新版'),
    noticeText: (t.match(/已按提示词[^\n]*/) || [''])[0],
    hasValidationError: t.includes('should have at least 1') || t.includes('material_ids') || t.includes('字段') && t.includes('List'),
    bodySnippet: t.slice(0, 80).replace(/\n/g, ' ')
  }
})
console.log('final:', JSON.stringify(final, null, 1))
console.log('console/network errors:', errs.slice(0, 5))
await page.screenshot({ path: 'D:/paper/dsh/platform-langgraph/shot-ai-optimize.png' })
await browser.close()
