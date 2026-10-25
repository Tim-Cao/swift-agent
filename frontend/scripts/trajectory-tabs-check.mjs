/**
 * v11.4 轨迹视图检查(CDP)。
 *
 * 覆盖:
 *  - 会话页**没有**智能体选择器(.agent-bar 不存在)
 *  - 轨迹视图**没有**元信息区域(.trajectory-header 不存在)
 *  - 浮动工具条存在(刷新 + 下载 JSONL)
 *  - system prompt 详情抽屉有两个标签页(系统提示词 / 工具)
 *  - 系统提示词标签页:没有「系统提示词(N 字符)」标签、内容区无边框、
 *    详情面板只有一条竖向滚动条
 *  - user 详情抽屉有四个标签页(概述 / 预览 / 原始内容 / 来源)
 *
 * 用法: CHECK_BASE=http://127.0.0.1:5188 node scripts/trajectory-tabs-check.mjs <sessionId>
 */
const CDP = 'http://127.0.0.1:9333'
const BASE = process.env.CHECK_BASE || 'http://127.0.0.1:5173'
// 后端地址:用来判断这条 user 消息**本来**有没有 source(老会话没有)
const API = process.env.CHECK_API || 'http://127.0.0.1:8000'
const sid = process.argv[2]

if (!sid) {
  console.error('用法: node scripts/trajectory-tabs-check.mjs <sessionId>')
  process.exit(1)
}

const res = await fetch(`${CDP}/json/new?${encodeURIComponent(`${BASE}/#/chat/${sid}`)}`, {
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
const evaluate = async (expr) => {
  const r = await send('Runtime.evaluate', {
    expression: expr,
    returnByValue: true,
    awaitPromise: true,
  })
  if (r.result?.exceptionDetails) {
    throw new Error(JSON.stringify(r.result.exceptionDetails))
  }
  return r.result?.result?.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** 等某个选择器出现(最多 timeout ms) */
const waitFor = async (selector, timeout = 8000) => {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const n = await evaluate(`document.querySelectorAll(${JSON.stringify(selector)}).length`)
    if (n > 0) return n
    await sleep(200)
  }
  return 0
}

await send('Page.enable')
await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', {
  width: 1440,
  height: 900,
  deviceScaleFactor: 2,
  mobile: false,
})
await sleep(2500)

const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok, detail })
  console.log(`${ok ? '✓' : '✗'} ${name}${detail ? ` — ${detail}` : ''}`)
}

// ---------- ① 会话页没有智能体选择器 ----------
const agentBar = await evaluate(`document.querySelectorAll('.agent-bar').length`)
check('会话页无智能体选择器', agentBar === 0, `.agent-bar x${agentBar}`)

// ---------- ② 切到轨迹 tab ----------
await evaluate(`
  (() => {
    const tabs = [...document.querySelectorAll('.tabs .tab')]
    const t = tabs.find((x) => x.textContent.includes('轨迹'))
    if (t) t.click()
    return !!t
  })()
`)
await sleep(2000)

// 等 timeline 渲染出来
await waitFor('.step-row')

// ---------- ③ 轨迹视图无元信息区域 ----------
const headerCount = await evaluate(`document.querySelectorAll('.trajectory-header').length`)
check('轨迹视图无元信息区域', headerCount === 0, `.trajectory-header x${headerCount}`)

// ---------- ④ 浮动工具条存在(只剩「下载 JSONL」,刷新按钮已移除) ----------
const toolbar = await evaluate(`
  (() => {
    const bar = document.querySelector('.floating-toolbar')
    if (!bar) return null
    return {
      buttons: bar.querySelectorAll('button').length,
      tips: [...bar.querySelectorAll('button')].map((b) => b.getAttribute('data-tip')),
    }
  })()
`)
check(
  '浮动工具条只剩「下载 JSONL」',
  !!toolbar && toolbar.buttons === 1 && (toolbar.tips[0] || '').includes('下载'),
  toolbar ? JSON.stringify(toolbar.tips) : '未找到 .floating-toolbar',
)

// ---------- ⑤ 点 system prompt 行 → 抽屉有两个标签页 ----------
await evaluate(`
  (() => {
    const row = document.querySelector('.step-row.kind-system')
    if (row) row.click()
    return !!row
  })()
`)
await sleep(800)
await waitFor('.details-pane .detail-tab')

const spTabs = await evaluate(`
  [...document.querySelectorAll('.details-pane .detail-tab')].map((t) => t.textContent.trim())
`)
check(
  'system prompt 抽屉有「系统提示词 / 工具」两个标签页',
  spTabs.length === 2 && spTabs[0].includes('系统提示词') && spTabs[1].includes('工具'),
  JSON.stringify(spTabs),
)

// ---------- ⑥ 系统提示词标签页:无字符数标签 / 内容区无边框 ----------
const spPrompt = await evaluate(`
  (() => {
    const body = document.querySelector('.details-pane-body')
    if (!body) return null
    const labels = [...body.querySelectorAll('.detail-label')].map((l) => l.textContent.trim())
    const pre = body.querySelector('.prompt-plain')
    const cs = pre ? getComputedStyle(pre) : null
    return {
      labels,
      hasCharCount: /系统提示词\\s*\\(\\d+\\s*字符\\)/.test(body.textContent || ''),
      border: cs ? cs.borderTopWidth + ' ' + cs.borderTopStyle : null,
      bg: cs ? cs.backgroundColor : null,
    }
  })()
`)
check(
  '系统提示词标签页无「系统提示词(N 字符)」标签',
  spPrompt && !spPrompt.hasCharCount && !spPrompt.labels.some((l) => /系统提示词\s*\(/.test(l)),
  spPrompt ? JSON.stringify(spPrompt.labels) : 'no body',
)
check(
  '系统提示词内容区无边框',
  spPrompt && /^0px/.test(spPrompt.border),
  spPrompt ? spPrompt.border : 'n/a',
)

// ---------- ⑦ 详情面板只有一条竖向滚动条 ----------
const scrollCheck = await evaluate(`
  (() => {
    const pane = document.querySelector('.details-pane')
    if (!pane) return null
    const scrollers = [...pane.querySelectorAll('*')].filter((el) => {
      const cs = getComputedStyle(el)
      const canScroll = /(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 1
      return canScroll
    })
    return {
      total: scrollers.length,
      classes: scrollers.map((el) => el.className || el.tagName),
    }
  })()
`)
check(
  '详情面板只有一条竖向滚动条',
  scrollCheck && scrollCheck.total <= 1,
  scrollCheck ? JSON.stringify(scrollCheck.classes) : 'no pane',
)

// ---------- ⑧ 工具标签页 ----------
await evaluate(`
  (() => {
    const tabs = [...document.querySelectorAll('.details-pane .detail-tab')]
    const t = tabs.find((x) => x.textContent.includes('工具'))
    if (t) t.click()
    return !!t
  })()
`)
await sleep(500)
const toolsTab = await evaluate(`
  (() => {
    const items = [...document.querySelectorAll('.details-pane .tool-item')]
    return {
      count: items.length,
      names: items.map((i) => i.querySelector('.tool-name')?.textContent?.trim()),
    }
  })()
`)
check(
  '「工具」标签页列出工具',
  toolsTab && toolsTab.count > 0,
  toolsTab ? JSON.stringify(toolsTab.names) : 'none',
)

// ---------- ⑨ 点 user 行 → 四个标签页 ----------
await evaluate(`
  (() => {
    const row = document.querySelector('.step-row.kind-user')
    if (row) row.click()
    return !!row
  })()
`)
await sleep(800)
await waitFor('.details-pane .detail-tab')
const userTabs = await evaluate(`
  [...document.querySelectorAll('.details-pane .detail-tab')].map((t) => t.textContent.trim())
`)
check(
  'user 抽屉有「概述 / 预览 / 原始内容 / 来源」四个标签页',
  userTabs.length === 4 &&
    userTabs[0].includes('概述') &&
    userTabs[1].includes('预览') &&
    userTabs[2].includes('原始内容') &&
    userTabs[3].includes('来源'),
  JSON.stringify(userTabs),
)

// ---------- ⑩ 来源标签页内容 ----------
await evaluate(`
  (() => {
    const tabs = [...document.querySelectorAll('.details-pane .detail-tab')]
    const t = tabs.find((x) => x.textContent.includes('来源'))
    if (t) t.click()
    return !!t
  })()
`)
await sleep(500)
const sourceTab = await evaluate(`
  (() => {
    const body = document.querySelector('.details-pane-body')
    if (!body) return null
    const keys = [...body.querySelectorAll('.meta-key')].map((k) => k.textContent.trim())
    const vals = [...body.querySelectorAll('.meta-val')].map((v) => v.textContent.trim())
    return { keys, vals, text: (body.textContent || '').slice(0, 300) }
  })()
`)

// 这条 user 消息在后端有没有 source?
//  - 有 → 「来源」标签页必须展示 kind / rpcId / clientTimeZone
//  - 没有(老会话)→ 必须展示明确的空态说明,不能是空白
let backendHasSource = false
try {
  const traj = await fetch(`${API}/api/sessions/${sid}/trajectory`).then((r) => r.json())
  backendHasSource = (traj.turns || []).some((t) => t.user_message_source)
} catch {
  backendHasSource = true // 拿不到就按「应该有」检查,宁严勿松
}

if (backendHasSource) {
  check(
    '「来源」标签页显示 kind / rpcId / clientTimeZone',
    sourceTab &&
      sourceTab.keys.includes('kind') &&
      sourceTab.keys.includes('rpcId') &&
      sourceTab.keys.includes('clientTimeZone'),
    sourceTab ? JSON.stringify(sourceTab.keys) : 'no body',
  )
} else {
  // 老会话:source 本来就没记录,要求显示空态提示
  const hasEmptyHint = /没有记录来源信息/.test(sourceTab?.text || '')
  check(
    '「来源」标签页(老会话无 source)显示空态说明',
    !!sourceTab && hasEmptyHint,
    sourceTab ? JSON.stringify(sourceTab.text?.slice(0, 60)) : 'no body',
  )
}

console.log('')
const failed = results.filter((r) => !r.ok)
console.log(`${results.length - failed.length}/${results.length} 通过`)
if (failed.length) {
  console.log('失败项:')
  for (const f of failed) console.log(`  - ${f.name} ${f.detail}`)
}

ws.close()
await fetch(`${CDP}/json/close/${target.id}`)
process.exit(failed.length ? 1 : 0)
