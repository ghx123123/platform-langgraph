// test-reparse-dsh.mjs — 验证文件预览里的"重新识别并保存"按钮: 任务发起 + 进度 + 完成
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/cc/projects/multi_agent_platform_langgraph/frontend/')
const { chromium } = require('playwright-core')

const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)) })
page.on('response', (r) => { if (r.status() >= 400) errs.push(`${r.status()} ${r.url().slice(-70)}`) })

await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2500)

// 展开 python 资料单元
await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => x.innerText && x.innerText.includes('python资料单元'))
  if (b) b.click()
})
await page.waitForTimeout(2500)

// 点击 01 章文件
const fileClicked = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('.unit-sources button')]
  const b = btns.find((x) => x.innerText && x.innerText.includes('01章'))
  if (b) { b.click(); return true; }
  if (btns[0]) { btns[0].click(); return true }
  return false
})
console.log('点击文件:', fileClicked)
await page.waitForTimeout(4000)

// 截图确认预览打开
await page.screenshot({ path: 'D:/paper/dsh/platform-langgraph/shot-reparse-before.png' })

// 点击"重新识别并保存"
const reparseClicked = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')]
  const b = btns.find((x) => x.innerText && x.innerText.includes('重新识别并保存'))
  if (b) { b.click(); return true }
  return false
})
console.log('点击重新识别:', reparseClicked)
await page.waitForTimeout(1200)

// 检查按钮状态变"识别中" 或进度出现
const parseState = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')]
  const progress = document.querySelector('progress')
  return {
    btnText: (btns.find((x) => x.innerText.includes('识别'))?.innerText || '')?.slice(0, 15),
    hasProgress: !!progress,
    progressValue: progress ? progress.value : null,
  }
})
console.log('解析状态:', JSON.stringify(parseState))
await page.screenshot({ path: 'D:/paper/dsh/platform-langgraph/shot-reparse-progress.png' })

// 等待完成
await page.waitForTimeout(15000)
const finalState = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')]
  const progress = document.querySelector('progress')
  return {
    btnText: (btns.find((x) => x.innerText.includes('识别'))?.innerText || '')?.slice(0, 15),
    hasProgress: !!progress,
    notice: (document.body.innerText.match(/已用 [^\n]{5,40}重新识别[^\n]{0,20}/) || [''])[0],
  }
})
console.log('最终:', JSON.stringify(finalState))
console.log('console 错误:', errs.slice(0, 5))
await browser.close()
