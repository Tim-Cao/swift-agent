/**
 * 检查「收起侧边栏」按钮的独立工具条。
 *
 * 背景:
 *   之前这个按钮是绝对定位浮在内容区左上角的,跟「智能体编辑页」的
 *   返回箭头(也在左上角)叠在一起(实测重叠 14×10px)。
 *   改成:按钮独占内容区顶部一行(.content-bar),
 *   和正文之间有一条分割线(.content-body 自己滚动)。
 *
 * 用法: CHECK_BASE=http://127.0.0.1:5173 node scripts/app-shell-bar-check.mjs
 */
import fs from 'node:fs'

const CDP = 'http://127.0.0.1:9333'
const BASE = process.env.CHECK_BASE || 'http://127.0.0.1:5173'

const checks = []
const check = (name, pass, detail = '') => {
  checks.push({ name, pass })
  console.log(`${pass ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`)
}

async function open(url) {
  const res = await fetch(`${CDP}/json/new?${encodeURIComponent(`${BASE}${url}`)}`, {
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
  await new Promise((r) => setTimeout(r, 3200))
  return { target, ws, send, evalJs }
}

const close = async (target, ws) => {
  ws.close()
  await fetch(`${CDP}/json/close/${target.id}`)
}

// ---------- 1) 智能体编辑页:两个图标不再重叠 ----------
{
  const { target, ws, evalJs } = await open('/#/agents/new')
  const geo = await evalJs(`
    (() => {
      const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { x: Math.round(b.x), y: Math.round(b.y), right: Math.round(b.right), bottom: Math.round(b.bottom) } }
      const c = r(document.querySelector('.collapse-btn'))
      const b = r(document.querySelector('.head-back'))
      const bar = r(document.querySelector('.content-bar'))
      const body = r(document.querySelector('.content-body'))
      let overlap = null
      if (c && b) {
        const w = Math.max(0, Math.min(c.right, b.right) - Math.max(c.x, b.x))
        const h = Math.max(0, Math.min(c.bottom, b.bottom) - Math.max(c.y, b.y))
        if (w > 0 && h > 0) overlap = { w, h }
      }
      return { c, b, bar, body, overlap }
    })()
  `)

  check('收起按钮和返回箭头不重叠', !geo?.overlap, geo?.overlap ? `重叠 ${geo.overlap.w}×${geo.overlap.h}px` : '')
  check('返回箭头在工具条下方', (geo?.b?.y ?? 0) >= (geo?.bar?.y ?? 0) + (geo?.bar ? 44 : 0),
    `back.y=${geo?.b?.y} bar.bottom=${geo?.bar?.y + 44}`)
  check('工具条独占一行(有高度)', (geo?.bar?.y === 0) && geo?.bar?.x >= 0, `bar=${JSON.stringify(geo?.bar)}`)

  await close(target, ws)
}

// ---------- 2) 工具条有分割线 ----------
{
  const { target, ws, evalJs } = await open('/#/agents')
  const bar = await evalJs(`
    (() => {
      const el = document.querySelector('.content-bar')
      if (!el) return null
      const s = getComputedStyle(el)
      return { borderBottom: s.borderBottomWidth, style: s.borderBottomStyle, color: s.borderBottomColor }
    })()
  `)
  check('工具条底部有分割线',
    parseFloat(bar?.borderBottom || '0') > 0 && bar?.style !== 'none',
    `${bar?.borderBottom} ${bar?.style}`)

  await close(target, ws)
}

// ---------- 3) 各页面:正文在工具条下方 + 不横向溢出 ----------
for (const [route, label, sel] of [
  ['/#/agents', '智能体管理', '.n-page'],
  ['/#/market', '智能体市场', '.n-page'],
  ['/#/tools', '工具管理', '.n-page'],
  ['/#/models', '模型管理', '.n-page'],
  ['/#/mcp', 'MCP 管理', '.n-page'],
  ['/#/chat', '新对话页', '.new-chat'],
  ['/#/agents/new', '智能体编辑页', '.editor'],
]) {
  const { target, ws, evalJs } = await open(route)
  const info = await evalJs(`
    (() => {
      const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { y: Math.round(b.y), h: Math.round(b.height) } }
      const bar = document.querySelector('.content-bar')
      const page = document.querySelector('${sel}')
      return {
        barH: r(bar)?.h,
        pageY: r(page)?.y,
        overflowX: document.documentElement.scrollWidth > window.innerWidth,
      }
    })()
  `)
  check(`${label}:正文在工具条下方`, (info?.pageY ?? 0) >= (info?.barH ?? 0), `page.y=${info?.pageY}`)
  check(`${label}:没有横向溢出`, info?.overflowX === false)
  await close(target, ws)
}

// ---------- 4) 聊天页(有会话):高度没被挤掉 ----------
{
  const { target, ws, evalJs } = await open('/#/chat')
  const clicked = await evalJs(`
    (() => {
      const li = document.querySelector('.session-list ul li')
      if (li) { li.click(); return true }
      return false
    })()
  `)
  await new Promise((r) => setTimeout(r, 3000))
  const info = await evalJs(`
    (() => {
      const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { y: Math.round(b.y), h: Math.round(b.height), bottom: Math.round(b.bottom) } }
      const win = document.querySelector('.chat-window')
      const input = document.querySelector('textarea')
      return {
        hash: location.hash,
        windowH: r(win)?.h,
        inputVisible: r(input) ? r(input).bottom <= window.innerHeight + 2 : null,
        docOverflow: document.documentElement.scrollHeight > window.innerHeight + 2,
      }
    })()
  `)
  check('聊天页:点开了会话', clicked === true, info?.hash)
  check('聊天页:窗口撑满剩余高度', (info?.windowH ?? 0) > 600, `${info?.windowH}px`)
  check('聊天页:输入框在视口内', info?.inputVisible === true)
  check('聊天页:文档不产生额外滚动', info?.docOverflow === false)
  await close(target, ws)
}

// ---------- 5) 收起态:工具条跟着侧边栏左移 ----------
{
  const { target, ws, evalJs } = await open('/#/agents')
  await evalJs(`document.querySelector('.collapse-btn').click()`)
  await new Promise((r) => setTimeout(r, 900))
  const info = await evalJs(`
    (() => {
      const sb = document.querySelector('.sidebar')
      const bar = document.querySelector('.content-bar')
      const shell = document.querySelector('.app-shell')
      const btn = document.querySelector('.collapse-btn')
      return {
        collapsed: shell?.classList.contains('sidebar-collapsed'),
        sidebarW: Math.round(sb.getBoundingClientRect().width),
        barX: Math.round(bar.getBoundingClientRect().x),
        flipped: getComputedStyle(btn).transform !== 'none',
      }
    })()
  `)
  check('收起态:侧边栏收窄', info?.collapsed === true && info?.sidebarW === 56, `${info?.sidebarW}px`)
  check('收起态:工具条跟着左移', info?.barX === 56, `bar.x=${info?.barX}`)
  check('收起态:图标翻转', info?.flipped === true)
  await close(target, ws)
}

const failed = checks.filter((c) => !c.pass)
console.log(`\n${checks.length - failed.length}/${checks.length} 项通过`)
process.exit(failed.length ? 1 : 0)
