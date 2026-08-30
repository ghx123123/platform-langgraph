// e2e-teacher-note-dlg.mjs — 教学补充对话框: 提示词→dsh生成→预览→保存→节点出现教学补充
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1700, height: 1050 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 90)) })
page.on('pageerror', (e) => errs.push('PAGEERR ' + String(e).slice(0,120)))

await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2200)
await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('python资料单元'))?.click())
await page.waitForTimeout(2200)
await page.evaluate(() => { const b=[...document.querySelectorAll('button')].find((x)=>x.innerText?.includes('打开最近大纲')); b?.click() })
await page.waitForTimeout(1500)

// 找一个没有教学补充的节点, 点"教学补充"添加按钮
const openBtn = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('.teacher-note-add-btn')]
  if (btns.length) { btns[0].click(); return { ok: true, label: btns[0].textContent } }
  // 没有空节点的, 点第一个"编辑"
  const eb = [...document.querySelectorAll('.teacher-note-edit-btn')][0]
  if (eb) { eb.click(); return { ok: true, label: 'edit' } }
  return { ok: false }
})
console.log('openTeacherNote:', JSON.stringify(openBtn))
await page.waitForTimeout(600)
const dlgInfo = await page.evaluate(() => {
  const dlg = document.querySelector('.teacher-note-dialog')
  return { present: !!dlg, hasTextarea: !!(dlg?.querySelector('textarea')) }
})
console.log('dlg:', JSON.stringify(dlgInfo))

// 输入提示词 (填第一个 textarea = 补充要求)
const setInstr = await page.evaluate(() => {
  const ta = document.querySelector('.teacher-note-dialog .teacher-note-body textarea')
  if (!ta) return false
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
  setter.call(ta, '补充一个与C语言相关的知识点')
  ta.dispatchEvent(new Event('input', { bubbles: true }))
  return true
})
console.log('setInstr:', setInstr)
await page.waitForTimeout(300)
// 点 dsh 生成
await page.evaluate(() => [...document.querySelectorAll('.teacher-note-dialog button')].find((x)=>x.innerText?.includes('dsh 生成'))?.click())
console.log('clicked generate, waiting dsh...')
await page.waitForTimeout(12000)
const genInfo = await page.evaluate(() => {
  const prev = document.querySelector('.teacher-note-preview')
  return { hasPreview: !!prev, previewLen: prev ? prev.value.length : 0, previewHead: prev ? prev.value.slice(0, 60) : '' }
})
console.log('genInfo:', JSON.stringify(genInfo))
await page.screenshot({ path: 'shot-teacher-note-dlg.png' })

// 同意导入(保存)
const saveInfo = await page.evaluate(() => {
  const b = [...document.querySelectorAll('.teacher-note-dialog button')].find((x)=>x.innerText?.includes('同意导入') || x.innerText?.includes('保存'))
  if (!b) return false
  b.click()
  return true
})
await page.waitForTimeout(1500)
console.log('saveInfo:', saveInfo)
// 确认节点出现教学补充
const afterInfo = await page.evaluate(() => {
  const t = document.body.innerText
  return { hasTeacherNoteTag: t.includes('教学补充'), dlgClosed: !document.querySelector('.teacher-note-dialog') }
})
console.log('afterInfo:', JSON.stringify(afterInfo))
await browser.close()
console.log('ERRORS:', errs.length, errs.slice(0, 4))
