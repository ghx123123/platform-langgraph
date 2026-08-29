// shot-final.mjs — 用户视角截图检测: 资料单元页 + 文件识别弹窗(满屏三栏)
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/cc/projects/multi_agent_platform_langgraph/frontend/')
const { chromium } = require('playwright-core')

const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 90)) })
page.on('pageerror', (e) => errs.push('PAGEERROR ' + String(e).slice(0, 90)))

// 1. 打开
await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2000)

// 2. 直接导航到资料单元页面 (SPA 路径 /materials)
await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2500) // 等 scope/units 加载
console.log('资料单元页:', await page.evaluate(() => document.body.innerText.includes('资料单元')))
await page.screenshot({ path: 'D:/paper/dsh/platform-langgraph/shot-unit-list.png' })

// 3. 点击 python资料单元 (展开)
const openedUnit = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')]
  const b = btns.find((x) => x.innerText && x.innerText.includes('python资料单元'))
  if (b) { b.click(); return true }
  return false
})
console.log('点击python单元:', openedUnit)
await page.waitForTimeout(3000)

// 4. 点击 当前资料 里的文件
const fileClicked = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('.unit-sources button')]
  const b = btns.find((x) => x.innerText && x.innerText.includes('数字图像处理'))
  if (b) { b.click(); return true }
  // 兜底: 任意文件
  if (btns[0]) { btns[0].click(); return true }
  return false
})
console.log('点击文件:', fileClicked)
await page.waitForTimeout(4500) // 等待 rawText 加载
await page.screenshot({ path: 'D:/paper/dsh/platform-langgraph/shot-file-preview.png' })

// 5. 打印 UI 状态
const info = await page.evaluate(() => {
  const t = document.body.innerText || ''
  const backdrop = document.querySelector('.file-preview-backdrop')
  const drawer = document.querySelector('.file-preview-drawer')
  return {
    hasPreview: !!backdrop,
    drawerWidth: drawer ? getComputedStyle(drawer).width : null,
    drawerHeight: drawer ? getComputedStyle(drawer).height : null,
    textHasPages: t.includes('解析后文本'),
    hasPageSep: t.includes('第 1 页') || t.includes('第1页'),
    screenshotHint: t.slice(0, 120)
  }
})
console.log('UI状态:', JSON.stringify(info, null, 1))
console.log('console errors:', errs.slice(0, 4))
await browser.close()
