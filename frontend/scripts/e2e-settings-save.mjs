// 面板完整流: 打开→选厂商DeepSeek→auto URL→填key→获取模型→选deepseek-v4-flash→保存→应用后 API 验证
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 100)) })
page.on('pageerror', (e) => errs.push('PAGEERR: ' + String(e).slice(0, 140)))
page.on('response', (r) => { if (r.status() >= 400 && r.url().includes('/api/settings')) errs.push(r.status() + ' ' + r.url().slice(-70)) })
await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2200)
await page.evaluate(() => document.querySelector('.model-quick-trigger')?.click())
await page.waitForTimeout(500)
await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('连接与参数设置'))?.click())
await page.waitForTimeout(800)
// 1) 选厂商 DeepSeek (自动填 URL + 推荐模型 deepseek-v4-flash)
const v = await page.evaluate(() => {
  const b = [...document.querySelectorAll('.vendor-control button')].find((x) => x.innerText === 'DeepSeek')
  if (!b) return null
  b.click()
  const url = [...document.querySelectorAll('.settings-dialog input')].find((x) => x.value?.includes('deepseek'))?.value
  const model = document.querySelector('.settings-dialog input[value="deepseek-v4-flash"], .model-picker select option[value="deepseek-v4-flash"]') ? 'deepseek-v4-flash' : 'n/a'
  return { url, model }
})
console.log('vendorDeepSeek:', JSON.stringify(v))
await page.waitForTimeout(300)
// 2) 填 key (从 env DEEPSEEK_API_KEY 拿 - 需从后端读取? 直接设置后保存)
const key = await page.evaluate(async () => {
  // 读取后端环境变量(仅用于测试渲染; 回退为空)
  try {
    const r = await fetch('/api/settings/model')
    const d = await r.json()
    return ''
  } catch { return '' }
})
// 从 node 端点拿 key 不方便; 直接保存(后端已有 DEEPSEEK_API_KEY env). 关键验证选中模型+自动URL
// 3) 点击"连接并获取模型" -> 应列出 dsh 模型
await page.evaluate(() => [...document.querySelectorAll('.settings-dialog button')].find((x) => x.innerText?.includes('连接并获取模型') || x.innerText?.includes('查看模型'))?.click())
await page.waitForTimeout(900)
const disc = await page.evaluate(() => ({
  state: document.querySelector('.connection-state')?.innerText,
  models: [...document.querySelectorAll('.settings-dialog .model-picker select option')].map((o) => o.value).filter(Boolean),
}))
console.log('discoverResult:', JSON.stringify(disc))
// 4) 选 deepseek-v4-flash 并保存
await page.evaluate(() => {
  const sel = document.querySelector('.settings-dialog .model-picker select')
  const opt = [...sel.options].find((o) => o.value === 'deepseek-v4-flash')
  if (opt) { sel.value = opt.value; sel.dispatchEvent(new Event('change', { bubbles: true })) }
})
await page.waitForTimeout(200)
await page.evaluate(() => {
  const b = [...document.querySelectorAll('.dialog-footer button')].find((x) => x.innerText?.includes('保存并应用'))
  if (b) b.click()
})
await page.waitForTimeout(1200)
const saved = await page.evaluate(async () => {
  const r = await fetch('/api/settings/model')
  const d = await r.json()
  return { provider: d.provider, model: d.model, base_url: d.base_url }
})
console.log('saved:', JSON.stringify(saved))
await page.screenshot({ path: 'shot-settings-saved.png' })
await browser.close()
console.log('ERRORS:', errs.length, errs.slice(0, 4))
