/**
 * 检查「MCP 管理」页的详情弹窗:
 *   - 点卡片 → 进详情弹窗(不是编辑弹窗)
 *   - 弹窗里有基本信息 + 工具区域
 *   - 工具渲染成卡片(名称 + 描述)
 *   - 有「同步工具」按钮
 *   - 卡片上有「编辑」图标,点它打开编辑弹窗
 *
 * 用法: CHECK_BASE=http://127.0.0.1:5199 node scripts/mcp-details-check.mjs
 */
import fs from 'node:fs'

const CDP = 'http://127.0.0.1:9333'
const BASE = process.env.CHECK_BASE || 'http://127.0.0.1:5173'

const res = await fetch(`${CDP}/json/new?${encodeURIComponent(`${BASE}/#/mcp`)}`, {
  method: 'PUT',
})
const target = await res.json()

let id = 0
const pending = new Map()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((r) => ws.addEventListener('open', r))
ws.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data)
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg)
    pending.delete(msg.id)
  }
})
const send = (method, params = {}) => {
  id += 1
  const myId = id
  ws.send(JSON.stringify({ id: myId, method, params }))
  return new Promise((resolve) => pending.set(myId, resolve))
}
const evalJs = async (expr) => {
  const r = await send('Runtime.evaluate', {
    expression: expr,
    returnByValue: true,
    awaitPromise: true,
  })
  if (r.result?.exceptionDetails) {
    return { __error: r.result.exceptionDetails.text }
  }
  return r.result?.result?.value
}

const errors = []
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

await send('Page.enable')
await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', {
  width: 1440,
  height: 900,
  deviceScaleFactor: 2,
  mobile: false,
})
await sleep(3500)

// 收集 console 错误
await evalJs(`
  window.__errs = []
  const oe = console.error
  console.error = (...a) => { window.__errs.push(a.map(String).join(' ')); oe(...a) }
  window.addEventListener('error', (e) => window.__errs.push('window.error: ' + e.message))
  true
`)

const checks = []
const check = (name, pass, detail = '') => {
  checks.push({ name, pass, detail })
  console.log(`${pass ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`)
}

// ---------- 1) 卡片存在 ----------
const cardCount = await evalJs(`document.querySelectorAll('.card-grid .card').length`)
check('MCP 卡片渲染出来了', cardCount > 0, `${cardCount} 张卡`)

if (!cardCount) {
  console.log('\n(没有卡片,后续检查跳过)')
  await send('Page.captureScreenshot', { format: 'png' }).then((s) => {
    fs.mkdirSync('/tmp/shots', { recursive: true })
    fs.writeFileSync('/tmp/shots/mcp-no-cards.png', Buffer.from(s.result.data, 'base64'))
  })
  ws.close()
  await fetch(`${CDP}/json/close/${target.id}`)
  process.exit(1)
}

// ---------- 2) 卡片上有「编辑」图标 ----------
const hasEditIcon = await evalJs(`
  (() => {
    const card = document.querySelector('.card-grid .card')
    if (!card) return false
    return !!card.querySelector('.icon-btn[data-tip="编辑"]')
  })()
`)
check('卡片上有「编辑」图标', hasEditIcon === true)

// ---------- 3) 点卡片 → 详情弹窗 ----------
await evalJs(`document.querySelector('.card-grid .card').click()`)
await sleep(1200)

const dialogInfo = await evalJs(`
  (() => {
    const dlg = document.querySelector('.el-dialog')
    if (!dlg) return { open: false }
    const title = dlg.querySelector('.el-dialog__title')?.textContent?.trim() || ''
    const text = dlg.textContent || ''
    return {
      open: true,
      title,
      text,
      hasBasic: text.includes('基本信息'),
      hasTools: text.includes('工具'),
      toolCards: dlg.querySelectorAll('.tool-card').length,
      toolNames: Array.from(dlg.querySelectorAll('.tool-name')).map((e) => e.textContent.trim()),
      hasSyncBtn: Array.from(dlg.querySelectorAll('button')).some((b) => b.textContent.includes('同步工具')),
      hasEditBtn: Array.from(dlg.querySelectorAll('button')).some((b) => b.textContent.trim() === '编辑'),
    }
  })()
`)

check('点卡片打开的是「详情」弹窗(不是编辑弹窗)', dialogInfo?.open === true, dialogInfo?.title || '')
check('弹窗标题是 MCP 名称', !!dialogInfo?.title && !dialogInfo.title.includes('新增 MCP'), dialogInfo?.title || '')
check('弹窗有「基本信息」区', dialogInfo?.hasBasic === true)
check('弹窗有「工具」区', dialogInfo?.hasTools === true)
check('弹窗有「同步工具」按钮', dialogInfo?.hasSyncBtn === true)
check('弹窗底部有「编辑」按钮', dialogInfo?.hasEditBtn === true)

// 工具卡片(后端同步过才有内容)
const toolCardCount = dialogInfo?.toolCards || 0
check('工具渲染成卡片', toolCardCount > 0, `${toolCardCount} 个工具卡片: ${(dialogInfo?.toolNames || []).join(', ')}`)

const toolCardShape = await evalJs(`
  (() => {
    const c = document.querySelector('.tool-card')
    if (!c) return null
    return {
      hasName: !!c.querySelector('.tool-name'),
      hasDesc: !!c.querySelector('.tool-desc'),
      descText: c.querySelector('.tool-desc')?.textContent?.trim() || '',
      hasParams: !!c.querySelector('.tool-params'),
      paramNames: Array.from(c.querySelectorAll('.tool-param')).map((e) => e.textContent.trim()),
    }
  })()
`)
check('工具卡片有名称', toolCardShape?.hasName === true)
check('工具卡片有描述', toolCardShape?.hasDesc === true, (toolCardShape?.descText || '').slice(0, 60) + '…')
check('工具卡片显示参数', toolCardShape?.hasParams === true, (toolCardShape?.paramNames || []).join(', '))

// 截图
const shot = await send('Page.captureScreenshot', { format: 'png' })
fs.mkdirSync('/tmp/shots', { recursive: true })
fs.writeFileSync('/tmp/shots/mcp-details.png', Buffer.from(shot.result.data, 'base64'))
console.log('\n截图: /tmp/shots/mcp-details.png')

// ---------- 4) 详情里点「编辑」→ 打开编辑弹窗 ----------
await evalJs(`
  (() => {
    const dlg = document.querySelector('.el-dialog')
    const btn = Array.from(dlg.querySelectorAll('button')).find((b) => b.textContent.trim() === '编辑')
    if (btn) { btn.click(); return true }
    return false
  })()
`)
await sleep(1200)

const editState = await evalJs(`
  (() => {
    const titles = Array.from(document.querySelectorAll('.el-dialog__title')).map((e) => e.textContent.trim())
    const visible = Array.from(document.querySelectorAll('.el-dialog')).filter((d) => d.offsetParent !== null)
    return { titles, visibleCount: visible.length, visibleTitles: visible.map((d) => d.querySelector('.el-dialog__title')?.textContent?.trim()) }
  })()
`)
check('详情里点「编辑」→ 打开编辑弹窗',
  (editState?.visibleTitles || []).some((t) => t?.includes('编辑 MCP')),
  JSON.stringify(editState?.visibleTitles))

// ---------- 5) 卡片上的编辑图标也能打开编辑弹窗 ----------
await evalJs(`
  (() => {
    document.querySelectorAll('.el-dialog__headerbtn').forEach((b) => b.click())
    return true
  })()
`)
await sleep(800)
await evalJs(`
  (() => {
    const card = document.querySelector('.card-grid .card')
    const btn = card?.querySelector('.icon-btn[data-tip="编辑"]')
    if (btn) { btn.click(); return true }
    return false
  })()
`)
await sleep(1200)
const iconEditState = await evalJs(`
  (() => {
    const visible = Array.from(document.querySelectorAll('.el-dialog')).filter((d) => d.offsetParent !== null)
    return visible.map((d) => d.querySelector('.el-dialog__title')?.textContent?.trim())
  })()
`)
check('卡片上的「编辑」图标 → 打开编辑弹窗',
  (iconEditState || []).some((t) => t?.includes('编辑 MCP')),
  JSON.stringify(iconEditState))

// ---------- console 错误 ----------
const errs = await evalJs(`window.__errs || []`)
if (errs && errs.length) {
  errors.push(...errs)
  check('没有 console 错误', false, errs.slice(0, 3).join(' | '))
} else {
  check('没有 console 错误', true)
}

const failed = checks.filter((c) => !c.pass)
console.log(`\n${checks.length - failed.length}/${checks.length} 项通过`)

ws.close()
await fetch(`${CDP}/json/close/${target.id}`)
process.exit(failed.length ? 1 : 0)
