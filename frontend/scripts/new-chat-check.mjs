/**
 * 新对话页 + 侧边栏重排的端到端检查(CDP)。
 *
 * 覆盖:
 *  - 侧边栏:应用名「Swift Agent」、主菜单「新对话 / 智能体市场」、
 *    「更多」分组默认收缩、历史会话在主菜单最下方
 *  - 新对话页:有智能体选择器、输入区
 *  - 发消息 → 建会话 → 跳到 /chat/:id
 *  - 点历史会话 → 跳到对应会话
 *
 * 用法: CHECK_BASE=http://127.0.0.1:5180 node scripts/new-chat-check.mjs
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
  if (ok) {
    console.log(`✓ ${label}`)
  } else {
    failed += 1
    console.log(`✗ ${label} ${extra}`)
  }
}

const target = await newTarget(`${BASE}/#/chat`)
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((r) => ws.addEventListener('open', r))
const c = cdp(ws)
await c.send('Runtime.enable')
await sleep(3500)

// ---------- 侧边栏 ----------
const side = await evalJs(c, `(() => {
  const sb = document.querySelector('.sidebar')
  if (!sb) return null
  const navItems = [...sb.querySelectorAll('.nav > .nav-item')].map(a => a.innerText.trim())
  const toggle = sb.querySelector('.nav-toggle')
  const subItems = [...sb.querySelectorAll('.nav-sub .nav-item')].map(a => a.innerText.trim())
  const history = sb.querySelector('.history')
  const historyIdx = history ? [...sb.children].indexOf(history.closest('.history')) : -1
  const navIdx = sb.querySelector('.nav') ? [...sb.children].indexOf(sb.querySelector('.nav')) : -1
  return {
    brand: sb.querySelector('.brand-name')?.innerText.trim(),
    navItems,
    toggleText: toggle?.innerText.trim(),
    toggleExpanded: toggle?.getAttribute('aria-expanded'),
    subItems,
    subVisible: !!sb.querySelector('.nav-sub') && getComputedStyle(sb.querySelector('.nav-sub')).display !== 'none',
    historyLabel: history?.querySelector('.history-label')?.innerText.trim(),
    hasHistoryList: !!history?.querySelector('.session-list'),
    orderOk: historyIdx > navIdx,
  }
})()`)

check('侧边栏: 应用名是 Swift Agent', side && side.brand === 'Swift Agent', JSON.stringify(side?.brand))
check(
  '侧边栏: 主菜单是新对话 + 智能体市场',
  side && side.navItems.join(',') === '新对话,智能体市场',
  JSON.stringify(side?.navItems),
)
check('侧边栏: 有「更多」分组', side && side.toggleText?.includes('更多'), JSON.stringify(side?.toggleText))
check('侧边栏: 「更多」默认收缩', side && side.toggleExpanded === 'false', JSON.stringify(side?.toggleExpanded))
check('侧边栏: 「更多」子项默认不可见', side && !side.subVisible, JSON.stringify(side?.subVisible))
check(
  '侧边栏: 「更多」里有四个管理页',
  side && side.subItems.join(',') === '智能体管理,工具管理,模型管理,MCP 管理',
  JSON.stringify(side?.subItems),
)
check('侧边栏: 有「最近」区', side && side.historyLabel === '最近', JSON.stringify(side?.historyLabel))
check('侧边栏: 最近区在主菜单下方', side && side.orderOk, JSON.stringify(side?.orderOk))

// 展开「更多」
await evalJs(c, `(() => { const t = document.querySelector('.nav-toggle'); if (t) t.click(); return true })()`)
await sleep(500)
const opened = await evalJs(c, `(() => {
  const sb = document.querySelector('.sidebar')
  const sub = sb.querySelector('.nav-sub')
  return {
    expanded: sb.querySelector('.nav-toggle')?.getAttribute('aria-expanded'),
    visible: sub ? getComputedStyle(sub).display !== 'none' : false,
  }
})()`)
check('侧边栏: 点「更多」能展开', opened.expanded === 'true' && opened.visible, JSON.stringify(opened))

// ---------- 新对话页 ----------
const page = await evalJs(c, `(() => {
  const inner = document.querySelector('.new-chat-inner')
  if (!inner) return null
  return {
    title: inner.querySelector('.hero-title')?.innerText.trim(),
    hasPicker: !!inner.querySelector('.picker'),
    chips: [...inner.querySelectorAll('.agent-chip')].map(b => b.innerText.trim()),
    hasComposer: !!inner.querySelector('.composer-box'),
    hasTextarea: !!inner.querySelector('.composer-box textarea'),
  }
})()`)
check('新对话: 页面打开', !!page, JSON.stringify(page))
check('新对话: 有大标题', page && page.title?.includes('可以帮你'), JSON.stringify(page?.title))
check('新对话: 有智能体选择器', page && page.hasPicker, JSON.stringify(page))
check('新对话: 选择器有「默认」选项', page && page.chips[0] === '默认', JSON.stringify(page?.chips))
check('新对话: 有输入框', page && page.hasComposer && page.hasTextarea, JSON.stringify(page))

// ---------- 发消息 → 建会话 ----------
const sent = await evalJs(c, `(() => {
  const ta = document.querySelector('.composer-box textarea')
  if (!ta) return false
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
  setter.call(ta, '新对话页测试消息')
  ta.dispatchEvent(new Event('input', { bubbles: true }))
  return true
})()`)
await sleep(400)
const clicked = await evalJs(c, `(() => {
  const btn = document.querySelector('.icon-btn[data-tip="发送(Enter)"]')
  if (!btn) return false
  btn.click()
  return true
})()`)
check('新对话: 点了发送', sent && clicked)

// 等流式结束(LLM 可能要几秒)—— 发完会跳到 /chat/:id
await sleep(12000)
const afterSend = await evalJs(c, `(() => ({
  hash: location.hash,
  hasMessages: !!document.querySelector('.bubble.user'),
}))()`)
check('新对话: 发送后跳到 /chat/:id', /^#\/chat\/[^/]+$/.test(afterSend.hash), JSON.stringify(afterSend))
check('新对话: 用户消息渲染出来了', afterSend.hasMessages, JSON.stringify(afterSend))

// ---------- 点历史会话能切回去 ----------
const hist = await evalJs(c, `(() => {
  const items = [...document.querySelectorAll('.history .session-list li')]
  return { count: items.length, first: items[0]?.innerText.trim() }
})()`)
check('侧边栏: 历史会话有记录', hist.count > 0, JSON.stringify(hist))

if (hist.count > 1) {
  // 点**第二个**(不是当前会话)→ URL 应该变
  const before = await evalJs(c, 'location.hash')
  await evalJs(c, `(() => {
    const items = [...document.querySelectorAll('.history .session-list li')]
    if (items[1]) items[1].click()
    return true
  })()`)
  await sleep(1500)
  const after = await evalJs(c, 'location.hash')
  check('侧边栏: 点历史会话能跳转', after !== before, `${before} → ${after}`)
}

// ---------- 回到新对话 ----------
await evalJs(c, `(() => {
  const a = [...document.querySelectorAll('.nav > .nav-item')].find(x => x.innerText.trim() === '新对话')
  if (a) a.click()
  return true
})()`)
await sleep(1200)
const backToNew = await evalJs(c, `(() => ({
  hash: location.hash,
  hasHero: !!document.querySelector('.hero-title'),
}))()`)
check('侧边栏: 点「新对话」回到落地页', backToNew.hash === '#/chat' && backToNew.hasHero, JSON.stringify(backToNew))

ws.close()
await fetch(`${CDP}/json/close/${target.id}`)
console.log(failed ? `\n${failed} 项失败` : '\n新对话流程全部正常')
process.exit(failed ? 1 : 0)
