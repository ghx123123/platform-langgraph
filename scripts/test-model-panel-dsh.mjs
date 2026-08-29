// test-model-panel-dsh.mjs — M6.4 前端 dsh 面板验证
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/cc/projects/multi_agent_platform_langgraph/frontend/')
const { chromium } = require('playwright-core')

const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)) })
page.on('pageerror', (e) => errs.push('PAGEERROR ' + String(e).slice(0, 120)))

await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2500)

// 打开模型快速切换菜单，然后点它的"连接与参数设置"（这才打开 Settings 面板）
const openedMenu = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => x.innerText.includes('当前模型') || x.title?.includes('替换当前模型'))
  if (b) { b.click(); return true }
  return false
})
console.log('打开快速切换菜单:', openedMenu)
await page.waitForTimeout(600)
const openedPanel = await page.evaluate(() => {
  const b = [...document.querySelectorAll('.model-quick-menu button')].find((x) => x.innerText.includes('连接与参数设置'))
  if (b) { b.click(); return true }
  return false
})
console.log('打开模型设置面板:', openedPanel)
await page.waitForTimeout(1500)

// 检查面板是否显示 dsh 智能体按钮
const hasDshBtn = await page.evaluate(() => document.body.innerText.includes('dsh 智能体'))
console.log('面板含 dsh 智能体按钮:', hasDshBtn)

// 点击 dsh 智能体按钮
const dshSelected = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('.provider-control button')]
  const b = btns.find((x) => x.innerText.includes('dsh'))
  if (b) { b.click(); return true }
  return false
})
console.log('选中 dsh:', dshSelected)
await page.waitForTimeout(600)

// 检查模型输入框是否变为 minimax-m3
const modelField = await page.evaluate(() => {
  const input = [...document.querySelectorAll('input')].find((i) => (i.value === 'minimax-m3'))
  return input ? input.value : null
})
console.log('模型字段:', modelField)

// 保存
const saved = await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => b.innerText.includes('保存并应用'))
  if (btn) { btn.click(); return true }
  return false
})
console.log('点击保存:', saved)
await page.waitForTimeout(1200)

// 查看 quick switcher
const quickText = await page.evaluate(() => {
  const t = document.body.innerText || ''
  return t.includes('dsh · minimax-m3') ? 'dsh · minimax-m3' : t.includes('minimax-m3') ? 'minimax-m3' : '未显示'
})
console.log('quick switcher:', quickText)

// 验证 API 实际生效
const apiResult = await page.evaluate(async () => {
  const r = await fetch('/api/settings/model')
  const d = await r.json()
  return { provider: d.provider, model: d.model }
})
console.log('API 现在:', JSON.stringify(apiResult))

// M6.5: 跳转资料单元页, 点击 AI 优化 → 输入提示词 → 生成 → 用 dsh+M3 真实生成
await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2500)
const unitOpen = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => x.innerText && x.innerText.includes('python资料单元'))
  if (b) { b.click(); return true }
  return false
})
console.log('单元展开:', unitOpen)
await page.waitForTimeout(2500)
const aiClick = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => x.innerText && x.innerText.trim().startsWith('AI 优化'))
  if (b) { b.click(); return true }
  return false
})
console.log('AI优化点击:', aiClick)
await page.waitForTimeout(800)
const sent = await page.evaluate(() => {
  const panel = document.querySelector('.refine-panel')
  if (!panel) return { ok: false }
  const ta = panel.querySelector('textarea')
  if (!ta) return { ok: false }
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
  setter.call(ta, '增加重难点解释，扩充知识点的详细说明')
  ta.dispatchEvent(new Event('input', { bubbles: true }))
  const b = [...panel.querySelectorAll('button')].find((x) => x.innerText.includes('生成优化版本'))
  if (b) { b.click(); return { ok: true } }
  return { ok: false }
})
console.log('发送优化:', JSON.stringify(sent))
await page.waitForTimeout(30000) // 等 M3 生成

const final = await page.evaluate(() => {
  const t = document.body.innerText || ''
  return {
    hasNotice: t.includes('已按提示词生成优化版本'),
    notice: (t.match(/已按提示词[^\n]{0,80}/) || [''])[0],
    hasErr: t.includes('should have at least') || t.includes('字段') || t.includes('error'),
  }
})
console.log('最终:', JSON.stringify(final))
await page.screenshot({ path: 'D:/paper/dsh/platform-langgraph/shot-ai-optimize-dsh.png' })
console.log('console 错误:', errs.slice(0, 4))
await browser.close()
