/**
 * 点「同步工具」按钮 → 后端真的连了一次 → 工具卡片刷新。
 *
 * 用法: CHECK_BASE=http://127.0.0.1:5199 node scripts/mcp-sync-check.mjs
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
  return r.result?.result?.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const checks = []
const check = (name, pass, detail = '') => {
  checks.push({ name, pass, detail })
  console.log(`${pass ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`)
}

await send('Page.enable')
await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', {
  width: 1440,
  height: 900,
  deviceScaleFactor: 2,
  mobile: false,
})
await sleep(3500)

// 打开详情
await evalJs(`document.querySelector('.card-grid .card').click()`)
await sleep(1200)

const before = await evalJs(`
  (() => {
    const dlg = document.querySelector('.el-dialog')
    return {
      tools: Array.from(dlg.querySelectorAll('.tool-name')).map((e) => e.textContent.trim()),
      count: dlg.querySelectorAll('.tool-card').length,
    }
  })()
`)
check('同步前已有工具卡片', before.count > 0, `${before.count} 个`)

// 点「同步工具」
const clicked = await evalJs(`
  (() => {
    const dlg = document.querySelector('.el-dialog')
    const btn = Array.from(dlg.querySelectorAll('button')).find((b) => b.textContent.includes('同步工具'))
    if (btn) { btn.click(); return true }
    return false
  })()
`)
check('找到并点了「同步工具」按钮', clicked === true)

// 等同步完成(会弹 toast)
await sleep(9000)

const after = await evalJs(`
  (() => {
    const dlg = document.querySelector('.el-dialog')
    const toast = document.querySelector('.el-message')
    return {
      tools: Array.from(dlg.querySelectorAll('.tool-name')).map((e) => e.textContent.trim()),
      count: dlg.querySelectorAll('.tool-card').length,
      toast: toast?.textContent?.trim() || '',
      toastType: toast?.className || '',
    }
  })()
`)
check('同步后工具卡片还在', after.count > 0, `${after.count} 个: ${after.tools.join(', ')}`)
check('同步没有报错', !after.toast.includes('失败'), after.toast || '(无 toast)')

const shot = await send('Page.captureScreenshot', { format: 'png' })
fs.mkdirSync('/tmp/shots', { recursive: true })
fs.writeFileSync('/tmp/shots/mcp-sync.png', Buffer.from(shot.result.data, 'base64'))
console.log('\n截图: /tmp/shots/mcp-sync.png')

const failed = checks.filter((c) => !c.pass)
console.log(`\n${checks.length - failed.length}/${checks.length} 项通过`)

ws.close()
await fetch(`${CDP}/json/close/${target.id}`)
process.exit(failed.length ? 1 : 0)
