import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 100)) })
page.on('pageerror', (e) => errs.push('PAGEERR: ' + String(e).slice(0, 140)))
await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2500)
// 打开 quick switcher 再点"连接与参数设置"
const clicked = await page.evaluate(() => {
  const trigger = document.querySelector('.model-quick-trigger') || [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('替换模型'))
  if (!trigger) return 'no-trigger'
  trigger.click()
  return 'trigger-clicked'
})
await page.waitForTimeout(700)
const openSettings = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('连接与参数设置'))
  if (!b) return document.body.innerText.slice(0, 200)
  b.click()
  return 'settings-open'
})
console.log('trigger:', clicked, '| openSettings:', openSettings)
await page.waitForTimeout(900)
const info = await page.evaluate(() => {
  const dlg = document.querySelector('.settings-dialog')
  if (!dlg) return { present: false }
  return { present: true, vendors: [...dlg.querySelectorAll('.vendor-control button')].map((b) => b.innerText), providerActive: dlg.querySelector('.provider-control .active')?.innerText }
})
console.log('panel:', JSON.stringify(info))
await page.screenshot({ path: 'shot-settings-open.png' })
await browser.close()
console.log('ERRORS:', errs.length)
