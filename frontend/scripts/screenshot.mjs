/**
 * 页面截图(CDP,不开 --no-sandbox)。
 * 用法: node scripts/screenshot.mjs
 * 产出: /tmp/shots/<name>.png
 */
import fs from 'node:fs'

const CDP = 'http://127.0.0.1:9333'
const BASE = 'http://127.0.0.1:5173'
const OUT = '/tmp/shots'

const PAGES = [
  { hash: '#/agents', name: 'agents' },
  { hash: '#/agents/new', name: 'agent-editor' },
  { hash: '#/market', name: 'market' },
  { hash: '#/tools', name: 'tools' },
  { hash: '#/models', name: 'models' },
  { hash: '#/chat', name: 'chat' },
]

fs.mkdirSync(OUT, { recursive: true })

async function newTarget(url) {
  const res = await fetch(`${CDP}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' })
  return res.json()
}

function cdp(ws) {
  let id = 0
  const pending = new Map()
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      pending.get(msg.id)(msg)
      pending.delete(msg.id)
    }
  })
  return {
    send(method, params = {}) {
      id += 1
      const myId = id
      ws.send(JSON.stringify({ id: myId, method, params }))
      return new Promise((resolve) => pending.set(myId, resolve))
    },
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

for (const page of PAGES) {
  const target = await newTarget(`${BASE}/${page.hash}`)
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r))
  const c = cdp(ws)
  await c.send('Page.enable')
  await c.send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 900,
    deviceScaleFactor: 2,
    mobile: false,
  })
  await sleep(2500)
  const shot = await c.send('Page.captureScreenshot', { format: 'png' })
  const file = `${OUT}/${page.name}.png`
  fs.writeFileSync(file, Buffer.from(shot.result.data, 'base64'))
  console.log(`✓ ${file}`)
  ws.close()
  await fetch(`${CDP}/json/close/${target.id}`)
}
