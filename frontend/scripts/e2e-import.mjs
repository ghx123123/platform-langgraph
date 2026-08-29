// e2e-import.mjs — 一键导入全部 e2e: 打开弹层 → 点击"一键导入全部" → 检查无 500
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE: ' + m.text().slice(0, 100)) })
page.on('pageerror', (e) => errs.push('PAGEERR: ' + String(e).slice(0, 120)))
page.on('response', (r) => { if (r.status() >= 400) errs.push(r.status() + ' ' + r.url().slice(-80)) })

await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2500)
await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('python资料单元'))?.click())
await page.waitForTimeout(2500)
const btn = await page.evaluate(() => {
  const b = document.querySelector('.graph-insert-btn')
  if (!b) return null
  b.click()
  return b.innerText
})
console.log('openBtn:', btn)
await page.waitForTimeout(1200)
const pickerInfo = await page.evaluate(() => ({
  dialog: !!document.querySelector('.gpi-dialog'),
  importBtnText: document.querySelector('.gpi-header-actions .gpi-btn-primary')?.innerText || '',
  treeRows: document.querySelectorAll('.gpi-tree-row').length,
}))
console.log('picker:', JSON.stringify(pickerInfo))
// 点击 一键导入全部
await page.evaluate(() => document.querySelector('.gpi-header-actions .gpi-btn-primary')?.click())
await page.waitForTimeout(3500)
const after = await page.evaluate(() => ({
  dialogOpen: !!document.querySelector('.gpi-dialog'),
  errBanner: document.body.innerText.includes('Unexpected server error') ? '500' : 'no500',
  noticeOrMsg: (document.querySelector('.material-unit-message')?.innerText || '').slice(0, 60),
}))
console.log('afterImport:', JSON.stringify(after))
await page.screenshot({ path: 'shot-import-done.png' })
await browser.close()
console.log('ERRORS:', errs.length, errs.slice(0, 6))
