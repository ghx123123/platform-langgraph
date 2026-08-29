import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } })
await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2200)
await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('python资料单元'))?.click())
await page.waitForTimeout(2200)
const gBtn = await page.evaluate(() => document.querySelector('.graph-insert-btn') !== null)
if (!gBtn) { console.log('NO BTN'); process.exit(1) }
await page.evaluate(() => document.querySelector('.graph-insert-btn').click())
await page.waitForTimeout(1200)
const geo = await page.evaluate(() => {
  const bb = (s) => { const el = document.querySelector(s); if (!el) return null; const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), bottom: Math.round(r.bottom) } }
  const foot = document.querySelector('.gpi-detail-foot')
  const btn = foot?.querySelector('button')
  const btnRect = btn ? btn.getBoundingClientRect() : null
  return {
    dialog: bb('.gpi-dialog'), body: bb('.gpi-body'), side: bb('.gpi-side'),
    canvas: bb('.gpi-canvas'), detail: bb('.gpi-detail'), riche: bb('.gpi-riche'),
    foot: bb('.gpi-detail-foot'), canvasTb: bb('.gpi-canvas-toolbar'),
    btnVisible: btnRect ? (btnRect.top >= 0 && btnRect.bottom <= window.innerHeight) : null,
    btnRect: btnRect ? { top: Math.round(btnRect.top), bottom: Math.round(btnRect.bottom) } : null,
    vh: window.innerHeight,
    scrollOverflow: (() => { const d = document.querySelector('.gpi-dialog'); return { ch: d.clientHeight, sh: d.scrollHeight } })(),
  }
})
console.log(JSON.stringify(geo, null, 1))
await browser.close()
