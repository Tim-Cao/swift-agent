/**
 * 「发现模型」端到端检查(CDP):点卡片上的放大镜 → 应发现 minimax 的模型,
 * 并出现在「模型」tab 里。
 * 用法: CHECK_BASE=http://127.0.0.1:5174 node scripts/discover-check.mjs
 */
const CDP = 'http://127.0.0.1:9333'
const BASE = process.env.CHECK_BASE || 'http://127.0.0.1:5173'

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

const target = await newTarget(`${BASE}/#/models`)
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((r) => ws.addEventListener('open', r))
const c = cdp(ws)
await c.send('Runtime.enable')
await sleep(3000)

// 页面上应该有「提供商」这个 tab
const tabs = await evalJs(c, `[...document.querySelectorAll('.el-tabs__item')].map(t => t.innerText.trim())`)
check('模型管理: 有「提供商」tab', tabs.includes('提供商'), JSON.stringify(tabs))
check('模型管理: 有「模型」tab', tabs.includes('模型'), JSON.stringify(tabs))

// 提供商卡片
const card = await evalJs(c, `(() => {
  const c = [...document.querySelectorAll('.card')].find(c => c.innerText.includes('MiniMax'))
  if (!c) return null
  return {
    text: c.innerText,
    hasSearch: !!c.querySelector('.icon-btn[data-tip="发现模型"]'),
  }
})()`)
check('提供商: 卡片存在', !!card, JSON.stringify(card))
check('提供商: 卡片有「发现模型」按钮', card && card.hasSearch, JSON.stringify(card))
check('提供商: base_url 是 minimax', card && card.text.includes('api.minimaxi.com'), JSON.stringify(card))
check(
  '提供商: 卡片显示「提供商 ID」',
  card && card.text.includes('提供商 ID'),
  JSON.stringify(card),
)
check(
  '提供商: 卡片不显示 API Key',
  card && !card.text.includes('Key '),
  JSON.stringify(card),
)
check(
  '提供商: 卡片不显示「OpenAI 兼容端点」',
  card && !card.text.includes('兼容端点'),
  JSON.stringify(card),
)

// 点「发现模型」
const clicked = await evalJs(c, `(() => {
  const c = [...document.querySelectorAll('.card')].find(c => c.innerText.includes('MiniMax'))
  if (!c) return false
  const btn = c.querySelector('.icon-btn[data-tip="发现模型"]')
  if (!btn) return false
  btn.click()
  return true
})()`)
await sleep(4000)

// 结果提示(ElMessage)不应该报鉴权失败
const msg = await evalJs(c, `document.querySelector('.el-message')?.innerText || ''`)
check('发现模型: 点击成功', clicked)
check('发现模型: 没有鉴权失败', !msg.includes('鉴权') && !msg.includes('401'), `msg=${msg}`)
console.log(`   提示: ${msg || '(无)'}`)

// 切到「模型」tab 看有没有 minimax 的模型
await evalJs(c, `(() => {
  const t = [...document.querySelectorAll('.el-tabs__item')].find(t => t.innerText.trim() === '模型')
  if (t) t.click()
  return true
})()`)
await sleep(1500)
const models = await evalJs(c, `[...document.querySelectorAll('.card')].map(c => c.innerText.split('\\n')[0])`)
check('模型: 发现到 minimax 模型', models.some(m => m.includes('MiniMax')), JSON.stringify(models))
console.log(`   模型: ${models.join(', ')}`)

ws.close()
await fetch(`${CDP}/json/close/${target.id}`)
console.log(failed ? `\n${failed} 项失败` : '\n发现模型流程正常')
process.exit(failed ? 1 : 0)
