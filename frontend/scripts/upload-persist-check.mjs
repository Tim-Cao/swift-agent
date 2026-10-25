/**
 * 上传的文件在**刷新页面后**仍然显示在气泡里(后端 meta.attachments → 前端 uploads)。
 * 用法: CHECK_BASE=http://127.0.0.1:5174 node scripts/upload-persist-check.mjs <zip路径>
 */
import fs from 'node:fs'

const CDP = 'http://127.0.0.1:9333'
const BASE = process.env.CHECK_BASE || 'http://127.0.0.1:5173'
const ZIP = process.argv[2] || '/tmp/testdata.zip'
// 每轮用唯一文本,便于在页面上定位本轮产生的那个气泡
const MARK = `上传持久化测试 ${process.pid}`

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

async function evalJs(c, expr) {
  const r = await c.send('Runtime.evaluate', {
    expression: expr,
    returnByValue: true,
    awaitPromise: true,
  })
  if (r.result?.exceptionDetails) {
    throw new Error(r.result.exceptionDetails.exception?.description || 'eval error')
  }
  return r.result?.result?.value
}

let failed = 0
function check(label, ok, extra = '') {
  console.log(ok ? `✓ ${label}` : `✗ ${label} ${extra}`)
  if (!ok) failed += 1
}

const target = await newTarget(`${BASE}/#/chat`)
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((r) => ws.addEventListener('open', r))
const c = cdp(ws)
await c.send('Runtime.enable')
await c.send('Page.enable')
await c.send('DOM.enable')
await sleep(3500)

// 上传
const doc = await c.send('DOM.getDocument')
const node = await c.send('DOM.querySelector', {
  nodeId: doc.result.root.nodeId,
  selector: '.composer-box input[type=file]',
})
await c.send('DOM.setFileInputFiles', { nodeId: node.result.nodeId, files: [ZIP] })
await sleep(2500)

await evalJs(c, `(() => {
  const ta = document.querySelector('.composer-box textarea')
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
  setter.call(ta, ${JSON.stringify(MARK)})
  ta.dispatchEvent(new Event('input', { bubbles: true }))
  return true
})()`)
await sleep(300)
await evalJs(c, `document.querySelector('.icon-btn[data-tip="发送(Enter)"]').click()`)
await sleep(3000)

// 后端 DB:确认 meta 落库 + 正文无前缀
const api = await evalJs(c, `(async () => {
  const list = await (await fetch('/api/sessions')).json()
  const items = Array.isArray(list) ? list : (list.items || list.sessions || [])
  const s = items[0]
  if (!s) return null
  const msgs = await (await fetch('/api/sessions/' + s.id + '/messages')).json()
  const arr = Array.isArray(msgs) ? msgs : (msgs.items || msgs.messages || [])
  const um = arr.filter(m => m.role === 'user' && String(m.content).includes(${JSON.stringify(MARK)})).slice(-1)[0]
  return { sessionId: s.id, meta: um ? um.meta : null, content: um ? um.content : null }
})()`)
check('后端: user 消息 meta.attachments 已落库', !!(api && api.meta?.attachments?.length), JSON.stringify(api))
check(
  '后端: 附件带 name/size_bytes',
  !!(api && api.meta?.attachments?.[0]?.name && api.meta.attachments[0].size_bytes != null),
  JSON.stringify(api),
)
check(
  '后端: 消息正文没有 [UPLOAD_DIR] 前缀',
  !!(api && !String(api.content || '').includes('[UPLOAD_DIR')),
  JSON.stringify(api),
)

// 刷新页面
await c.send('Page.reload', {})
await sleep(4000)

const after = await evalJs(c, `(() => {
  const bubbles = [...document.querySelectorAll('.bubble.user')]
  const mine = bubbles.find(b => b.innerText.includes(${JSON.stringify(MARK)}))
  if (!mine) return { found: false, bubbles: bubbles.length }
  return {
    found: true,
    cards: mine.querySelectorAll('.upload-card').length,
    names: [...mine.querySelectorAll('.upload-card .file-name')].map(n => n.innerText),
  }
})()`)
check('刷新后: 本轮气泡里仍有文件卡', after && after.found && after.cards === 1, JSON.stringify(after))
check(
  '刷新后: 文件名正确',
  after && after.names.some((n) => n.includes('testdata.zip')),
  JSON.stringify(after),
)

const shot = await c.send('Page.captureScreenshot', { format: 'png' })
fs.writeFileSync('/tmp/shots/upload-persist.png', Buffer.from(shot.result.data, 'base64'))
console.log('saved /tmp/shots/upload-persist.png')

ws.close()
await fetch(`${CDP}/json/close/${target.id}`)
console.log(failed ? `\n${failed} 项失败` : '\n刷新后附件仍在气泡中')
process.exit(failed ? 1 : 0)
