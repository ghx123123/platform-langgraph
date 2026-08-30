// e2e-outline-history.mjs — 验证历史大纲版本列表弹窗: 打开/显示版本/删除一个
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 100)) })
page.on('pageerror', (e) => errs.push('PAGEERR: ' + String(e).slice(0, 140)) )
page.on('response', (r) => { if (r.status() >= 400) errs.push(r.status() + ' ' + r.url().slice(-70)) })

await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2200)
await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('python资料单元'))?.click())
await page.waitForTimeout(2200)

// 确认 outline 已生成(有版本 select)
const hasOutline = await page.evaluate(() => !!document.querySelector('.outline-panel header select'))
console.log('hasOutline:', hasOutline)
// 切到含多版本的大纲组(取 select 里最后一个 option, 通常是另一组或有历史)
await page.evaluate(() => {
  const sel = document.querySelector('.outline-panel header select')
  if (!sel || sel.options.length < 2) return
  const opt = sel.options[sel.options.length - 1]  // 选最后一个(可能是含历史组)
  sel.value = opt.value
  sel.dispatchEvent(new Event('change', { bubbles: true }))
})
await page.waitForTimeout(800)

// 打开版本历史按钮
const histBtn = await page.evaluate(() => {
  const b = document.querySelector('.outline-history-btn')
  if (!b) return false
  b.click()
  return true
})
await page.waitForTimeout(600)
console.log('histBtnOpen:', histBtn)

const info = await page.evaluate(() => {
  const dlg = document.querySelector('.outline-history-dialog')
  if (!dlg) return { open: false }
  const rows = [...dlg.querySelectorAll('.outline-history-row')]
  return {
    open: true,
    count: rows.length,
    current: rows.find((r) => r.querySelector('.outline-history-current'))?.innerText?.replace(/\s+/g, ' ').slice(0, 40) || null,
    delBtns: dlg.querySelectorAll('.outline-history-del').length,
  }
})
console.log('historyDialog:', JSON.stringify(info))
await page.screenshot({ path: 'shot-outline-history.png' })

// 删除一个历史版本(点非当前的删除按钮)
let delHappened = false
await page.evaluate(() => {
  const dlg = document.querySelector('.outline-history-dialog')
  const del = dlg?.querySelector('.outline-history-del')
  if (del) { del.click(); return true }
  return false
})
delHappened = true
await page.waitForTimeout(700)
const afterDel = await page.evaluate(() => {
  const confirm = [...document.querySelectorAll('.unit-dialog')].find((x) => x.innerText?.includes('删除知识大纲'))
  return { confirmDialog: !!confirm }
})
console.log('deleteClicked:', JSON.stringify(afterDel))
await page.screenshot({ path: 'shot-outline-history-del.png' })

await browser.close()
console.log('ERRORS:', errs.length, errs.slice(0, 4))
