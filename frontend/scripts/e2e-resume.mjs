// e2e-resume.mjs — 模拟"思考中关闭再进"：发问题→立刻关预览→重开→检查问题恢复+续聊可用
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE: ' + m.text().slice(0, 90)) })
page.on('pageerror', (e) => errs.push('PAGEERR: ' + String(e).slice(0, 120)))
page.on('response', (r) => { if (r.status() >= 400) errs.push(r.status() + ' ' + r.url().slice(-80)) })

async function openFile() {
  await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2200)
  await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('python资料单元'))?.click())
  await page.waitForTimeout(2200)
  // 打开一个已解析教材(Python程序设计基础与应用_第01章)
  const fileBtn = await page.evaluate(() => {
    const b = [...document.querySelectorAll('.unit-sources > button')].find((x) => x.innerText?.includes('Python程序设计基础与应用'))
    if (b) { b.click(); return b.innerText.slice(0, 30) }
    return null
  })
  console.log('openFile:', fileBtn)
  await page.waitForTimeout(1800)
  return !!fileBtn
}

// 1) 打开文件
const ok1 = await openFile()
if (!ok1) { console.log('FAIL: file not found'); process.exit(1) }

// 2) 找到基于节点的讨论(点击已保存节点旁"基于节点讨论"若存在), 填问题, 发送(不等待LLM完成)
const question = '这部电视剧里的python是什么意思'
const sent = await page.evaluate((q) => {
  const input = [...document.querySelectorAll('input')].find((x) => x.placeholder && x.placeholder.includes('讨论问题'))
  if (!input) return { ok: false }
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
  setter.call(input, q)
  input.dispatchEvent(new Event('input', { bubbles: true }))
  const btn = [...document.querySelectorAll('button')].find((x) => x.innerText?.trim() === '发送' || x.innerText?.trim() === '思考中…')
  if (!btn) return { ok: false, found: false }
  btn.click()
  return { ok: true, btn: btn.innerText }
}, question)
console.log('sent:', JSON.stringify(sent))

// 3) 等 1s 就立刻关闭预览(思考中), 模拟用户关闭
await page.waitForTimeout(1000)
const close1 = await page.evaluate(() => {
  const b = document.querySelector('.file-preview-backdrop button[aria-label="关闭"], .file-preview-drawer > header button, .file-preview-backdrop header button')
  // 关闭预览的按钮在 header 内
  const all = [...document.querySelectorAll('.file-preview-backdrop header button, .file-preview-drawer > header button')]
  const btn = all.find((x) => x.getAttribute('aria-label') === '关闭' || x.title === '关闭') || all[0]
  if (btn) { btn.click(); return true }
  return false
})
console.log('closedDuringThinking:', close1)
await page.waitForTimeout(600)

// 4) 立刻重新打开同一文件
const ok2 = await openFile()
console.log('reopened:', ok2)
await page.waitForTimeout(1500)

// 5) 检查问题是否恢复(rounds 列表里应出现该问题)
const restored = await page.evaluate((q) => {
  const text = [...document.querySelectorAll('.file-preview-backdrop *')].filter((e) => e.innerText && e.innerText.includes(q) && e.children.length === 0).map((e) => e.innerText.slice(0, 40))
  return { found: text.slice(0, 3), inputVal: [...document.querySelectorAll('input')].find((x) => x.placeholder?.includes('讨论问题'))?.value || '' }
}, question)
console.log('restored:', JSON.stringify(restored))
await page.screenshot({ path: 'shot-resume.png' })
await browser.close()
console.log('ERRORS:', errs.length, errs.slice(0, 4))
