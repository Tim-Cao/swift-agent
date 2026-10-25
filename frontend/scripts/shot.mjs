/**
 * 截图当前页面(CDP)。
 * 用法: CHECK_BASE=http://127.0.0.1:5180 node scripts/shot.mjs <hash> <name> [w] [h]
 */
import fs from 'node:fs'

const CDP = 'http://127.0.0.1:9333'
const BASE = process.env.CHECK_BASE || 'http://127.0.0.1:5173'
const hash = process.argv[2] || '/chat'
const name = process.argv[3] || 'shot'
const w = Number(process.argv[4] || 1440)
const h = Number(process.argv[5] || 900)

const res = await fetch(`${CDP}/json/new?${encodeURIComponent(`${BASE}/#${hash}`)}`, {
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

await send('Page.enable')
await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', {
  width: w,
  height: h,
  deviceScaleFactor: 2,
  mobile: false,
})
await new Promise((r) => setTimeout(r, 3500))

const shot = await send('Page.captureScreenshot', { format: 'png' })
fs.mkdirSync('/tmp/shots', { recursive: true })
const out = `/tmp/shots/${name}.png`
fs.writeFileSync(out, Buffer.from(shot.result.data, 'base64'))
console.log(out)

ws.close()
await fetch(`${CDP}/json/close/${target.id}`)
