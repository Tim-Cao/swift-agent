/**
 * 上传 → 发送 → 文件卡进气泡的端到端检查(CDP)。
 * 用法: node scripts/upload-check.mjs <zip路径>
 */
import fs from 'node:fs'

const CDP = 'http://127.0.0.1:9333'
const BASE = 'http://127.0.0.1:5173'
const ZIP = process.argv[2] || '/tmp/testdata.zip'

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

// 找到上传按钮(隐藏的 file input)
const doc = await c.send('DOM.getDocument')
const node = await c.send('DOM.querySelector', {
  nodeId: doc.result.root.nodeId,
  selector: '.composer-box input[type=file]',
})
check('输入区: 找到 file input', node.result.nodeId > 0)

// 往 file input 里塞文件
const fileData = fs.readFileSync(ZIP).toString('base64')
await c.send('DOM.setFileInputFiles', {
  nodeId: node.result.nodeId,
  files: [ZIP],
})
await sleep(2500)

const hint = await evalJs(c, `document.querySelector('.uploaded-hint')?.innerText || ''`)
check('输入区: 上传后显示文件名', hint.includes('testdata.zip'), `hint=${hint}`)

// 输入文字
await evalJs(c, `(() => {
  const ta = document.querySelector('.composer-box textarea')
  if (!ta) return false
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
  setter.call(ta, '看看这个 zip 里的数据')
  ta.dispatchEvent(new Event('input', { bubbles: true }))
  return true
})()`)
await sleep(400)

// 点发送
await evalJs(c, `(() => {
  const btn = document.querySelector('.icon-btn[data-tip="发送(Enter)"]')
  if (!btn) return false
  btn.click()
  return true
})()`)
await sleep(2500)

// 用户气泡里应该有文件卡
const bubble = await evalJs(c, `(() => {
  const b = document.querySelector('.bubble.user')
  if (!b) return null
  return {
    text: b.innerText,
    cards: b.querySelectorAll('.upload-card').length,
    names: [...b.querySelectorAll('.upload-card .file-name')].map(n => n.innerText),
    chipOutside: !!document.querySelector('.input-bar .attachment-chip'),
  }
})()`)
check('气泡: 用户消息里有文件卡', bubble && bubble.cards === 1, JSON.stringify(bubble))
check(
  '气泡: 文件名正确',
  bubble && bubble.names.some((n) => n.includes('testdata.zip')),
  JSON.stringify(bubble),
)
check('输入区: 文件卡已从输入框移走', bubble && bubble.chipOutside === false)

// 截图留证
const shot = await c.send('Page.captureScreenshot', { format: 'png' })
fs.writeFileSync('/tmp/shots/upload-bubble.png', Buffer.from(shot.result.data, 'base64'))
console.log('saved /tmp/shots/upload-bubble.png')

ws.close()
await fetch(`${CDP}/json/close/${target.id}`)
console.log(failed ? `\n${failed} 项失败` : '\n上传流程全部正常')
process.exit(failed ? 1 : 0)
