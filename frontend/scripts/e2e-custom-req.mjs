// e2e-custom-req.mjs — 验证大纲要求自定义补充: 选讲次→匹配→补充自定义→勾选→生成大纲→大纲含自定义(不产节点)
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')
const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1050 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 100)) })
page.on('pageerror', (e) => errs.push('PAGEERR: ' + String(e).slice(0, 120)) )
page.on('response', (r) => { if (r.status() >= 400 && r.url().includes('/api/material-units')) errs.push(r.status() + ' ' + r.url().slice(-60)) })

// 处理 window.prompt
page.on('dialog', async (d) => {
  // 依次回答: 标题/分类/内容
  if (d.type() === 'prompt') {
    const seq = promptSeq++
    if (seq === 0) await d.accept('教师补充：短路求值')
    else if (seq === 1) await d.accept('knowledge')
    else if (seq === 2) await d.accept('Python and/or 的短路求值特性')
    else await d.dismiss()
  } else await d.dismiss()
})
let promptSeq = 0

await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2200)
await page.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('python资料单元'))?.click())
await page.waitForTimeout(2200)

// 选一个讲次(步骤1 第1个)
const selSess = await page.evaluate(() => {
  const b = document.querySelectorAll('.session-options > button')[0]
  if (!b) return false
  b.click()
  return true
})
console.log('selectSession:', selSess)
// 等待匹配完成(loading 消失)
for (let i = 0; i < 20; i++) {
  await page.waitForTimeout(500)
  const busy = await page.evaluate(() => !!document.querySelector('.alignment-content .inline-loading'))
  if (!busy) break
}

// 补充自定义要求(点"＋补充要求", prompt 由 dialog 处理)
const diag = await page.evaluate(() => {
  const content = document.querySelector('.alignment-content')
  return {
    hasContent: !!content,
    contentHtmlLen: content ? content.innerHTML.length : 0,
    hasCustomBtn: !!document.querySelector('.custom-req-add button'),
    step2Text: (content?.innerText || '').slice(0, 120),
  }
})
console.log('diag:', JSON.stringify(diag))
const addBtn = await page.evaluate(() => !!document.querySelector('.custom-req-add button'))
console.log('addBtnPresent:', addBtn)
await page.evaluate(() => document.querySelector('.custom-req-add button')?.click())
await page.waitForTimeout(400)
const customVisible = await page.evaluate(() => {
  const t = document.body.innerText
  return { hasCustom: t.includes('教师补充：短路求值'), hasCustomGroup: t.includes('教师自定义/补充') }
})
console.log('customVisible:', JSON.stringify(customVisible))
await page.screenshot({ path: 'shot-custom-req.png' })

// 生成大纲(需先有讲次+至少一个勾选; 勾第一个匹配项)
await page.evaluate(() => {
  const cb = document.querySelector('.alignment-content .requirement-group:not(.is-custom) input[type="checkbox"]')
  cb?.click()
})
await page.waitForTimeout(300)
await page.evaluate(() => {
  const g = [...document.querySelectorAll('button')].find((x) => x.innerText?.includes('生成知识大纲'))
  g?.click()
})
await page.waitForTimeout(2500)
// 检查大纲面板是否生成
const outlineInfo = await page.evaluate(() => {
  const t = document.body.innerText
  return { generated: t.includes('第 1 版') || t.includes('知识大纲'), hasCustomNode: false }
})
// 查后端大纲里 requirements 含自定义但不产节点
const apiCheck = await page.evaluate(async () => {
  const r = await fetch('/api/material-units/8bb8a5fa-2770-42df-ace4-b4fe8445daf4/knowledge-outlines?include_versions=true')
  const d = await r.json()
  const latest = d.items?.[0]
  if (!latest) return { none: true }
  const customs = (latest.requirements || []).filter((x) => x.custom)
  const nodeTitles = (latest.nodes || []).map((n) => n.title)
  return {
    hasCustomReq: customs.length > 0,
    customTitles: customs.map((c) => c.title),
    customMadeNode: customs.some((c) => nodeTitles.includes(c.title)),
  }
})
console.log('outlineInfo:', JSON.stringify(outlineInfo))
console.log('apiCheck:', JSON.stringify(apiCheck))
await page.screenshot({ path: 'shot-custom-req-done.png' })

await browser.close()
console.log('ERRORS:', errs.length, errs.slice(0, 4))
