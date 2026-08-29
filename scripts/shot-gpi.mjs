// shot-gpi.mjs — 验证 "图谱导入知识大纲" 三栏工作台弹层
import { createRequire } from 'node:module'
const require = createRequire('D:/paper/dsh/platform-langgraph/frontend/')
const { chromium } = require('playwright-core')

const EXE = 'C:/Users/84652/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe'
const browser = await chromium.launch({ headless: true, executablePath: EXE, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 140)) })
page.on('pageerror', (e) => errs.push('PAGEERR ' + String(e).slice(0, 160)))
page.on('response', (r) => { if (r.status() >= 400) errs.push(`${r.status()} ${r.url().slice(-90)}`) })

await page.goto('http://127.0.0.1:5173/materials', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2500)

const unitOpen = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => x.innerText && x.innerText.includes('python资料单元'))
  if (b) { b.click(); return true }
  return false
})
console.log('unitOpen:', unitOpen)
await page.waitForTimeout(2500)

// 大纲树中找 📖 教材研读按钮
const gBtn = await page.evaluate(() => {
  const b = document.querySelector('.graph-insert-btn')
  return b ? { text: b.innerText, title: b.getAttribute('title') } : null
})
console.log('graphInsertBtn:', JSON.stringify(gBtn))
if (!gBtn) {
  console.log('no graph insert btn, screen text sample:', (await page.evaluate(() => document.body.innerText.slice(0, 400))))
  await page.screenshot({ path: 'shot-gpi-nobtn.png' })
  await browser.close()
  process.exit(1)
}
await page.evaluate(() => document.querySelector('.graph-insert-btn').click())
await page.waitForTimeout(1500)

// 结构检查: 三栏是否出现
const layout = await page.evaluate(() => {
  const sel = (s) => Boolean(document.querySelector(s))
  const info = {
    dialog: sel('.gpi-dialog'), header: sel('.gpi-header'), body: sel('.gpi-body'),
    side: sel('.gpi-side'), tabs: sel('.gpi-side-tabs'), search: sel('.gpi-search'),
    chips: sel('.gpi-chips'), tree: sel('.gpi-tree'), treeRows: document.querySelectorAll('.gpi-tree-row').length,
    canvas: sel('.gpi-canvas'), layoutSwitch: sel('.gpi-layout-switch'), note: sel('.gpi-canvas-note'),
    svg: sel('.gv-svg'), graphNodes: document.querySelectorAll('.gv-svg g > g').length,
    detail: sel('.gpi-detail'), props: document.querySelectorAll('.gpi-prop-grid label').length,
    riche: sel('.gpi-riche'), secs: document.querySelectorAll('.gpi-sec').length,
    bigBtn: document.querySelector('.gpi-detail-foot button')?.innerText || '',
    zoomLabel: document.querySelector('.gpi-zoomval')?.innerText || '',
  }
  info.bodyText = (document.querySelector('.gpi-body')?.innerText || '').slice(0, 300)
  return info
})
console.log('layout:', JSON.stringify(layout, null, 1))
await page.screenshot({ path: 'shot-gpi.png' })

// 折叠测试: 点击中心根节点的折叠按钮(第一个 g 内的 circle 后 group)
const foldInfo = await page.evaluate(() => {
  // 找 SVG 内带有 title 含 "折叠子节点" 的 g
  const titleEls = [...document.querySelectorAll('.gv-svg g title')].map((t) => t.textContent)
  const foldable = titleEls.filter((t) => t && t.includes('折叠'))
  if (!foldable.length) return { found: 0 }
  // 点击第一个折叠按钮: 第三个子 g(btn group) 在节点 render 内部
  const nodeGs = document.querySelectorAll('.gv-svg g > g')
  for (const g of nodeGs) {
    const t = g.querySelector('title')?.textContent || ''
    if (t.includes('点击 − 折叠子节点')) {
      const btns = [...g.querySelectorAll('g')]
      if (btns.length) { btns[btns.length - 1].dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })) }
      return { found: 1, title: t }
    }
  }
  return { found: 1, viaFallback: 1, note: foldable }
})
console.log('foldInfo:', JSON.stringify(foldInfo))
await page.waitForTimeout(600)
const after = await page.evaluate(() => ({
  nodeGs: document.querySelectorAll('.gv-svg g > g').length,
  t: (document.querySelector('.gpi-canvas-note')?.innerText || ''),
}))
console.log('after fold:', JSON.stringify(after))
await page.screenshot({ path: 'shot-gpi-folded.png' })

// 右侧 Accordion 展开第二个区块
const accInfo = await page.evaluate(() => {
  const secs = [...document.querySelectorAll('.gpi-sec > header')]
  if (secs[1]) { secs[1].click(); return { clicked: secs[1].innerText.slice(0, 20) } }
  return { clicked: null }
})
console.log('accInfo:', JSON.stringify(accInfo))
await page.waitForTimeout(400)
await page.screenshot({ path: 'shot-gpi-accord.png' })

// 缩放测试
const zoomInfo = await page.evaluate(() => {
  const plus = [...document.querySelectorAll('.gpi-canvas-toolbar button')].find((b) => b.title === '放大')
  for (let i = 0; i < 2; i++) plus?.click()
  return { clicked: Boolean(plus) }
})
await page.waitForTimeout(300)
console.log('zoomInfo:', JSON.stringify(zoomInfo), await page.evaluate(() => document.querySelector('.gpi-zoomval')?.innerText))
await page.screenshot({ path: 'shot-gpi-zoom.png' })

// 点击左侧搜索 + chip 测试
const chipInfo = await page.evaluate(() => {
  const b = [...document.querySelectorAll('.gpi-chips button')].find((x) => x.innerText.includes('根节点'))
  b?.click()
  return { ok: Boolean(b), rowsAfter: document.querySelectorAll('.gpi-tree-row').length }
})
console.log('chipInfo:', JSON.stringify(chipInfo))
await page.waitForTimeout(300)
await page.screenshot({ path: 'shot-gpi-chip.png' })

await browser.close()
console.log('ERRORS:', errs.length, errs.slice(0, 6))
