/**
 * 浏览器渲染检查(用 CDP,不开 --no-sandbox)。
 *
 * 打开每个页面,等它把数据拉回来,然后 dump DOM 检查关键内容 + 收集控制台错误。
 * 前置:前端 dev server 在 :5173,后端在 :8000。
 * 用法: node scripts/browser-check.mjs
 */
const CDP = 'http://127.0.0.1:9333'
const BASE = 'http://127.0.0.1:5173'

const PAGES = [
  { hash: '#/agents', expect: ['智能体管理', 'Supervisor'] },
  { hash: '#/market', expect: ['智能体市场'] },
  { hash: '#/tools', expect: ['工具管理', '写 Excel'] },
  { hash: '#/models', expect: ['模型管理', '提供商'] },
  { hash: '#/chat', expect: ['会话工作区', '使用智能体'] },
]

async function newTarget(url) {
  const res = await fetch(`${CDP}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' })
  return res.json()
}

function cdp(ws) {
  let id = 0
  const pending = new Map()
  const events = []
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      pending.get(msg.id)(msg)
      pending.delete(msg.id)
    } else if (msg.method) {
      events.push(msg)
    }
  })
  return {
    send(method, params = {}) {
      id += 1
      const myId = id
      ws.send(JSON.stringify({ id: myId, method, params }))
      return new Promise((resolve) => pending.set(myId, resolve))
    },
    events,
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

let failed = 0
for (const page of PAGES) {
  const target = await newTarget(`${BASE}/${page.hash}`)
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r))
  const c = cdp(ws)
  await c.send('Runtime.enable')
  await c.send('Log.enable')
  await c.send('Page.enable')
  await sleep(2500)

  const res = await c.send('Runtime.evaluate', {
    expression: 'document.body.innerText',
    returnByValue: true,
  })
  const text = res.result?.result?.value || ''

  const errors = c.events
    .filter((e) => e.method === 'Log.entryAdded' && e.params.entry.level === 'error')
    .map((e) => e.params.entry.text)
    .filter((t) => !/favicon|404 \(Not Found\)/.test(t))

  const missing = page.expect.filter((t) => !text.includes(t))
  if (missing.length || errors.length) {
    failed += 1
    console.log(`✗ ${page.hash}`)
    if (missing.length) console.log(`   缺少内容: ${missing.join(', ')}`)
    if (errors.length) console.log(`   控制台错误: ${errors.slice(0, 3).join(' | ')}`)
    console.log(`   实际文本前 300 字: ${text.slice(0, 300).replace(/\n/g, ' / ')}`)
  } else {
    console.log(`✓ ${page.hash} — 渲染正常 (${text.length} 字符)`)
  }
  ws.close()
  await fetch(`${CDP}/json/close/${target.id}`)
}

console.log(failed ? `\n${failed} 个页面有问题` : '\n全部页面渲染正常')
process.exit(failed ? 1 : 0)
