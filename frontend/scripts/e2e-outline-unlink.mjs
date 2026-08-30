// 验证: 大纲节点教学补充里列出多个图谱, 每个可指定取消(不再 find 第一个)
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1700, height: 1050 } })
const errs = []
page.on('pageerror', (e) => errs.push('PAGEERR ' + String(e).slice(0,120)))
page.on('dialog', (d) => d.accept())  // 自动接受 confirm
await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2200)
await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('python资料单元'))?.click())
await page.waitForTimeout(2200)
// 打开最近大纲(右侧可能有第1章节点含教材研读补充)
await page.evaluate(() => { const b=[...document.querySelectorAll('button')].find((x)=>x.innerText?.includes('打开最近大纲')); b?.click() })
await page.waitForTimeout(1200)
await page.evaluate(() => [...document.querySelectorAll('.outline-tree details.node-teacher-note summary')].find((s)=>s.innerText?.includes('教学补充'))?.click())
await page.waitForTimeout(500)
const info = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('.graph-unlink-list .graph-unlink-btn')]
  return { unlinkBtns: btns.length, btnLabels: btns.map(b => b.textContent.replace(/\s+/g,'').slice(0,18)) }
})
console.log('outlineSide unlink list:', JSON.stringify(info))
await page.screenshot({ path: 'shot-outline-unlink-list.png' })
// 点第2个取消导入按钮(讲其中一集的故事), 只删它
await page.evaluate(() => [...document.querySelectorAll('.graph-unlink-list .graph-unlink-btn')][1]?.click())
await page.waitForTimeout(900)
const after = await page.evaluate(async () => {
  const b = [...document.querySelectorAll('.graph-unlink-list .graph-unlink-btn')]
  return { remainBtns: b.length, labels: b.map(x => x.textContent.replace(/\s+/g,'').slice(0,18)) }
})
console.log('after unlink#2:', JSON.stringify(after))
await browser.close()
console.log('ERR:', errs.length)
