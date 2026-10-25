/**
 * 打开「新建工具」弹窗并截图(看拖拽上传区)。
 * 用法: CHECK_BASE=http://127.0.0.1:5176 node scripts/shot-dialog.mjs
 */
import fs from 'node:fs'

const CDP = 'http://127.0.0.1:9333'
const BASE = process.env.CHECK_BASE || 'http://127.0.0.1:5173'

const res = await fetch(`${CDP}/json/new?${encodeURIComponent(`${BASE}/#/tools`)}`, {
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

await send('Page.enable')
await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', {
  width: 1440,
  height: 900,
  deviceScaleFactor: 2,
  mobile: false,
})
await new Promise((r) => setTimeout(r, 3000))

// 点「新建工具」
await evalJs(`(() => {
  const btn = document.querySelector('.icon-btn[data-tip="新建工具"]')
  if (btn) { btn.click(); return true }
  return false
})()`)
await new Promise((r) => setTimeout(r, 1200))

const shot = await send('Page.captureScreenshot', { format: 'png' })
fs.mkdirSync('/tmp/shots', { recursive: true })
fs.writeFileSync('/tmp/shots/tool-editor-drop.png', Buffer.from(shot.result.data, 'base64'))
console.log('/tmp/shots/tool-editor-drop.png')

ws.close()
await fetch(`${CDP}/json/close/${target.id}`)
