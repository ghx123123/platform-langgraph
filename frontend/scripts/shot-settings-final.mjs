import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2200)
await page.evaluate(() => document.querySelector('.model-quick-trigger')?.click())
await page.waitForTimeout(400)
await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('连接与参数设置'))?.click())
await page.waitForTimeout(900)
await page.screenshot({ path: 'shot-settings-final.png' })
await browser.close()
void createRequire
