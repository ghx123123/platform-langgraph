// e2e-graph-imports.mjs — 图谱面板: 节点显示导入位置 + 取消导入
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 90)) })
page.on('pageerror', (e) => errs.push('PAGEERR: ' + String(e).slice(0, 120)) )
page.on('response', (r) => { if (r.status() >= 400 && r.url().includes('/api/material-units')) errs.push(r.status() + ' ' + r.url().slice(-70)) })

await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2200)
await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('python资料单元'))?.click())
await page.waitForTimeout(2200)
// 打开一个教材 PDF 预览
await page.evaluate(() => [...document.querySelectorAll('.unit-sources > button')].find((x) => x.innerText?.includes('Python程序设计基础与应用_第01章'))?.click())
await page.waitForTimeout(1800)

// 展开"已保存图谱节点"
const openNodes = await page.evaluate(() => {
  const s = [...document.querySelectorAll('summary')].find((x) => x.innerText?.includes('已保存图谱节点'))
  if (!s) return false
  s.click()
  return true
})
await page.waitForTimeout(600)
console.log('openNodes:', openNodes)

// 查看某个节点是否显示"已导入到知识大纲"
const importsInfo = await page.evaluate(() => {
  // 列出每个图谱节点的导入位置卡片(富文本节点卡片)
  const cards = [...document.querySelectorAll('b')].filter(b => b.textContent?.includes('主角叫啥') || b.textContent?.includes('举一个例子'))
  const cardText = cards.map(c => c.parentElement?.parentElement?.innerText?.slice(0,120)).join('
---
')
  return { nodeCards: cards.length, cardSample: cardText.slice(0, 300) }
})
console.log('cardSample:', JSON.stringify(importsInfo))
await page.screenshot({ path: 'shot-graph-multi.png' })
const importsInfo2 = await page.evaluate(() => {
  const t = document.body.innerText
  const hasMarked = t.includes('已导入到知识大纲')
  const unlinkBtns = [...document.querySelectorAll('button[title*="取消导入"]')].length
  return { hasMarked, unlinkBtns, textSlice: t.slice(0, 0) }
})
console.log('importsInfo:', JSON.stringify(importsInfo))
await page.screenshot({ path: 'shot-graph-imports.png' })

// 点第一个"取消导入"
const unlink = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button[title*="取消导入"]')][0]
  if (!b) return false
  b.click()
  return true
})
await page.waitForTimeout(900)
console.log('clickedUnlink:', unlink)

// 查后端: 该节点导入记录应减少
const afterApi = await page.evaluate(async () => {
  const r = await fetch('/api/material-units/8bb8a5fa-2770-42df-ace4-b4fe8445daf4/graph-nodes/graph-a1befec8df/outline-imports')
  const d = await r.json()
  return { remainingImports: d.items?.length || 0 }
})
console.log('afterApi:', JSON.stringify(afterApi))
await page.screenshot({ path: 'shot-graph-imports-after.png' })
await browser.close()
console.log('ERRORS:', errs.length, errs.slice(0, 4))
