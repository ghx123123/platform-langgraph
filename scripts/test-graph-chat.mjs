// test-graph-chat.mjs — M7 阅读图谱端到端: 打开预览 → 图谱面板 → 选词 → 提问 → 保存图谱节点 → 截图
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/cc/projects/multi_agent_platform_langgraph/frontend/')
const { chromium } = require('playwright-core')

const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox'] })
const page = await browser.newPage({ viewport: { width: 1720, height: 1050 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 100)) })
page.on('pageerror', (e) => errs.push('PAGEERROR ' + String(e).slice(0, 100)))

await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2600)
await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find((x) => x.innerText.includes('python资料单元')); if (b) b.click() })
await page.waitForTimeout(3000)
// 打开 01 章预览
await page.evaluate(() => { const b = [...document.querySelectorAll('.unit-sources button')].find((x) => x.innerText.includes('01章')); if (b) b.click() })
await page.waitForTimeout(4000)
// 检查阅读图谱面板存在
const hasGraph = await page.evaluate(() => document.body.innerText.includes('阅读图谱'))
console.log('阅读图谱面板:', hasGraph)
// 模拟选词: 直接设置 quote + 提问
const q1 = await page.evaluate(() => {
  const input = [...document.querySelectorAll('input')].find((i) => i.placeholder.includes('输入讨论问题'))
  if (!input) return { ok: false }
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
  setter.call(input, 'import 和 from import 的教学区别？')
  input.dispatchEvent(new Event('input', { bubbles: true }))
  const btn = [...document.querySelectorAll('button')].find((x) => x.innerText.trim() === '发送')
  if (btn) { btn.click(); return { ok: true } }
  return { ok: false }
})
console.log('提问1:', JSON.stringify(q1))
await page.waitForTimeout(35000) // 等 dsh 回答
// 显示回答?
const after1 = await page.evaluate(() => {
  const t = document.body.innerText || ''
  return { hasAnswer: t.includes('助手') || t.includes('import'), answerText: (t.match(/助手[\s\S]{0,60}/) || [''])[0].slice(0, 50) }
})
console.log('第1轮后:', JSON.stringify(after1))
await page.screenshot({ path: 'D:/paper/dsh/platform-langgraph/shot-graph-chat-1.png' })

// 多轮: 第二次提问, 同 chat_id 续聊
const q2 = await page.evaluate(() => {
  const input = [...document.querySelectorAll('input')].find((i) => i.placeholder.includes('输入讨论问题'))
  if (!input) return { ok: false }
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
  setter.call(input, '学生最容易混淆哪里？')
  input.dispatchEvent(new Event('input', { bubbles: true }))
  const btn = [...document.querySelectorAll('button')].find((x) => x.innerText.trim() === '发送')
  if (btn) { btn.click(); return { ok: true } }
  return { ok: false }
})
console.log('提问2(多轮):', JSON.stringify(q2))
await page.waitForTimeout(30000)
const after2 = await page.evaluate(() => {
  const t = document.body.innerText || ''
  return { hasTwoQA: (t.match(/教师/g) || []).length >= 2 }
})
console.log('多轮后:', JSON.stringify(after2))

// 保存图谱节点
const saved = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => x.innerText.includes('保存为图谱节点'))
  if (b) { b.click(); return true } return false
})
console.log('保存图谱节点:', saved)
await page.waitForTimeout(35000)
const afterSave = await page.evaluate(() => {
  const t = document.body.innerText || ''
  return { hasNodes: t.includes('已保存图谱节点'), nodeTitle: (t.match(/已保存图谱节点（\d+）/ ) || [''])[0] }
})
console.log('保存后:', JSON.stringify(afterSave))
await page.screenshot({ path: 'D:/paper/dsh/platform-langgraph/shot-graph-chat-2.png' })
console.log('errors:', errs.slice(0, 5))
await browser.close()
