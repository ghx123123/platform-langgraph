// e2e-teacher-note.mjs — 编辑大纲模式下改/删减教学补充(teacher_note)
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 90)) })
page.on('pageerror', (e) => errs.push('PAGEERR: ' + String(e).slice(0, 120)) )

await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2200)
await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('python资料单元'))?.click())
await page.waitForTimeout(2200)
// 打开最近大纲(若有)
await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('打开最近大纲')); b?.click() })
await page.waitForTimeout(1500)

// 点击"编辑大纲"
const edit = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => x.innerText?.trim() === '编辑大纲')
  if (!b) return false
  b.click()
  return true
})
await page.waitForTimeout(600)
console.log('editOutline:', edit)

// 检查老师补充 textarea 是否出现
const editorInfo = await page.evaluate(() => {
  const tas = [...document.querySelectorAll('.node-teacher-editor')]
  return { textareaCount: tas.length, firstValLen: tas[0] ? tas[0].value.length : 0 }
})
console.log('editor:', JSON.stringify(editorInfo))

// 修改第一个有内容的 teacher_note: 删减(清空 or 缩短)
const mod = await page.evaluate(() => {
  const tas = [...document.querySelectorAll('.node-teacher-editor')]
  const target = tas.find((t) => t.value.trim().length > 10)
  if (!target) return { mod: false }
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
  setter.call(target, target.value.slice(0, 60) + '【已删减】')
  target.dispatchEvent(new Event('input', { bubbles: true }))
  return { mod: true, newVal: target.value.slice(0, 70) }
})
console.log('modify:', JSON.stringify(mod))
await page.screenshot({ path: 'shot-teacher-note-edit.png' })

// 保存新版本
const save = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('保存新版本'))
  if (!b) return false
  b.click()
  return true
})
await page.waitForTimeout(2500)
console.log('saveVersion:', save)

// 校验后端: 最新大纲里该节点 teacher_note 已减
const apiCheck = await page.evaluate(async () => {
  const r = await fetch('/api/material-units/8bb8a5fa-2770-42df-ace4-b4fe8445daf4/knowledge-outlines?include_versions=true')
  const d = await r.json()
  const latest = d.items?.find((o) => (o.requirements || []).some((x) => x.custom === undefined)) || d.items[0]
  const nodes = latest?.nodes || []
  const withNote = nodes.find((n) => (n.teacher_note || '').includes('已删减'))
  return { latestVersion: latest?.version, deletedTagged: !!withNote }
})
console.log('apiCheck:', JSON.stringify(apiCheck))
await browser.close()
console.log('ERRORS:', errs.length, errs.slice(0, 4))
