import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox','--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1700, height: 1050 } })
const errs = []
page.on('pageerror', (e)=>errs.push('PAGE '+String(e).slice(0,100)))
await page.goto('http://127.0.0.1:5173/materials', { waitUntil:'domcontentloaded' })
await page.waitForTimeout(2200)
await page.evaluate(()=>[...document.querySelectorAll('button')].find(x=>x.innerText?.includes('python资料单元'))?.click())
await page.waitForTimeout(2200)
// 检查分隔条
const splits = await page.evaluate(()=>({ count: document.querySelectorAll('.mu-split').length, widths: [...document.querySelectorAll('.unit-sidebar,.outline-panel')].map(e=>Math.round(e.getBoundingClientRect().width)) }))
console.log('splits:', JSON.stringify(splits))
// 用 playwright 原生 mouse 拖动分隔条(真实 pointer 事件)
const pos = await page.evaluate(()=>{
  const s = document.querySelector('.mu-split[data-split="0"]')
  const r = s.getBoundingClientRect()
  return { x: r.x + r.width/2, y: r.y + 200 }
})
await page.mouse.move(pos.x, pos.y)
await page.mouse.down()
await page.mouse.move(pos.x + 100, pos.y, { steps: 8 })  // 向右拖 side 变宽
await page.mouse.up()
await page.waitForTimeout(400)
const after = await page.evaluate(()=>({ sideW: Math.round(document.querySelector('.unit-sidebar').getBoundingClientRect().width), outlineW: Math.round(document.querySelector('.outline-panel').getBoundingClientRect().width) }))
console.log('after drag split0 +100 (side变宽):', JSON.stringify(after))
await page.screenshot({ path:'shot-split.png' })
await browser.close()
console.log('ERR:', errs.length)
