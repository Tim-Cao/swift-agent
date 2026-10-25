/**
 * 交互流程检查(CDP):智能体新建/编辑页(两栏 + 工具选择弹窗)、工具上传、模型提供商、
 * 输入区(共用外框 + 底部图标行)、圆形图标按钮。
 * 用法: node scripts/flow-check.mjs
 */
import fs from 'node:fs'

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

/** 在 Vue 里给某个 <el-input> 的原生 input 赋值并触发 input 事件 */
const SET_INPUT = (selector, value) => `(() => {
  const el = document.querySelector(${JSON.stringify(selector)})
  if (!el) return false
  const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement : window.HTMLInputElement
  const setter = Object.getOwnPropertyDescriptor(proto.prototype, 'value').set
  setter.call(el, ${JSON.stringify(value)})
  el.dispatchEvent(new Event('input', { bubbles: true }))
  return true
})()`

/** 按 title 找一个 .icon-btn(圆形图标按钮)并点击 */
const CLICK_ICON = (title, scope = 'document') => `(() => {
  const root = ${scope}
  const btn = root.querySelector('.icon-btn[data-tip="' + ${JSON.stringify(title)} + '"]')
  if (!btn) return false
  btn.click()
  return true
})()`

// ---------- 1. 智能体:新建页面(两栏) ----------
{
  const target = await newTarget(`${BASE}/#/agents/new`)
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r))
  const c = cdp(ws)
  await c.send('Runtime.enable')
  await sleep(2500)

  // 只看编辑器区域(侧边栏有「模型管理」导航,会误判)
  const bodyText = await evalJs(c, `document.querySelector('.editor')?.innerText || ''`)
  check('智能体: 新建页打开', bodyText.includes('新建智能体'))
  check('智能体: 左栏有名称字段', bodyText.includes('名称'))
  check('智能体: 左栏有提示词字段', bodyText.includes('提示词'))
  check('智能体: 右栏有工具面板', bodyText.includes('工具'))
  check('智能体: 不再显示描述字段', !bodyText.includes('描述'))
  check('智能体: 不再显示模型字段', !bodyText.includes('模型'))

  // 保存草稿 / 发布 是纯图标圆形按钮(没有文字)
  const hasSave = await evalJs(c, `!!document.querySelector('.icon-btn[data-tip="保存草稿"]')`)
  const hasPublish = await evalJs(c, `!!document.querySelector('.icon-btn[data-tip="发布"]')`)
  check('智能体: 有保存草稿按钮', hasSave)
  check('智能体: 有发布按钮', hasPublish)

  // 左右两栏确实是两个 .pane
  const paneCount = await evalJs(c, `document.querySelectorAll('.pane').length`)
  check('智能体: 左右两个面板', paneCount === 2, `pane=${paneCount}`)

  // 填名称 + 提示词
  const named = await evalJs(c, SET_INPUT('.name-input input', 'UI测试Agent'))
  await sleep(200)
  const prompted = await evalJs(c, SET_INPUT('.prompt-input textarea', '你是一个测试用的智能体。'))
  await sleep(300)
  check('智能体: 名称可填', named)
  check('智能体: 提示词可填', prompted)

  // 点「选择工具」打开工具选择弹窗
  const opened = await evalJs(c, CLICK_ICON('选择工具', `document.querySelector('.pane-right')`))
  await sleep(700)
  const dlgText = await evalJs(c, `document.querySelector('.el-dialog')?.innerText || ''`)
  check('智能体: 工具选择弹窗打开', opened && dlgText.includes('确定'))
  check('智能体: 弹窗列出可用工具', /execute_pandas_code|inspect_csv|unzip_archive|write_excel/.test(dlgText))

  // 勾一个工具并确定
  const picked = await evalJs(c, `(() => {
    const dlg = document.querySelector('.el-dialog')
    if (!dlg) return false
    const boxes = [...dlg.querySelectorAll('.el-checkbox')]
    if (!boxes.length) return false
    boxes[0].click()
    return true
  })()`)
  await sleep(300)
  await evalJs(c, `(() => {
    const dlg = document.querySelector('.el-dialog')
    const btn = [...dlg.querySelectorAll('button')].find(b => b.textContent.trim() === '确定')
    if (btn) btn.click()
  })()`)
  await sleep(700)
  const boundCount = await evalJs(c, `document.querySelectorAll('.bound-tool').length`)
  check('智能体: 工具绑定到右栏', picked && boundCount >= 1, `bound=${boundCount}`)

  // 保存草稿 → 应跳到编辑页
  await evalJs(c, CLICK_ICON('保存草稿', `document.querySelector('.editor-head')`))
  await sleep(1800)
  const afterSave = await evalJs(c, `document.querySelector('.editor')?.innerText || ''`)
  const url = await evalJs(c, 'location.hash')
  check('智能体: 保存草稿后进入编辑页', afterSave.includes('编辑智能体'), `url=${url}`)
  const nameVal = await evalJs(c, `document.querySelector('.name-input input')?.value || ''`)
  check('智能体: 草稿页回填名称', nameVal === 'UI测试Agent', `name=${nameVal}`)

  // 回列表并清理
  await evalJs(c, `(() => {
    const back = document.querySelector('.head-back')
    if (back) back.click()
    return true
  })()`)
  await sleep(1500)
  const listText = await evalJs(c, `document.querySelector('.n-page')?.innerText || ''`)
  check('智能体: 列表出现 UI测试Agent', listText.includes('UI测试Agent'))

  const deleted = await evalJs(c, `(() => {
    const cards = [...document.querySelectorAll('.card')]
    const card = cards.find(c => c.innerText.includes('UI测试Agent'))
    if (!card) return false
    const btn = card.querySelector('.icon-btn[data-tip="删除"]')
    if (!btn) return false
    btn.click()
    return true
  })()`)
  await sleep(500)
  await evalJs(c, `(() => {
    const btn = [...document.querySelectorAll('.el-message-box button')].find(b => b.textContent.trim() === '删除')
    if (btn) btn.click()
  })()`)
  await sleep(1200)
  const after = await evalJs(c, `document.querySelector('.n-page')?.innerText || ''`)
  check('智能体: 删除生效', deleted && !after.includes('UI测试Agent'))

  ws.close()
  await fetch(`${CDP}/json/close/${target.id}`)
}

// ---------- 2. 智能体市场 ----------
{
  const target = await newTarget(`${BASE}/#/market`)
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r))
  const c = cdp(ws)
  await c.send('Runtime.enable')
  await sleep(2500)

  const bodyText = await evalJs(c, 'document.body.innerText')
  check('市场: 页面打开', bodyText.includes('智能体市场'))
  check('市场: 无「内置」标签', !bodyText.includes('内置'))
  const cardCount = await evalJs(c, `document.querySelectorAll('.card').length`)
  check('市场: 有已发布卡片', cardCount > 0, `cards=${cardCount}`)

  ws.close()
  await fetch(`${CDP}/json/close/${target.id}`)
}

// ---------- 3. 工具:新建/编辑弹窗里的拖拽上传区 ----------
{
  const target = await newTarget(`${BASE}/#/tools`)
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r))
  const c = cdp(ws)
  await c.send('Runtime.enable')
  await sleep(2500)

  // 页面头部不再有「上传 zip 包」图标按钮
  const hasUploadBtn = await evalJs(
    c,
    `!!document.querySelector('.icon-btn[data-tip="上传 zip 包"]')`,
  )
  check('工具: 头部没有单独的「上传 zip 包」按钮', !hasUploadBtn)

  // 「新建工具」弹窗里应该有拖拽上传区
  const opened = await evalJs(c, CLICK_ICON('新建工具'))
  await sleep(800)
  const dlg = await evalJs(c, `document.querySelector('.el-dialog')?.innerText || ''`)
  check('工具: 新建弹窗打开', opened && dlg.includes('工具名称'), dlg.slice(0, 80))

  const drop = await evalJs(c, `(() => {
    const d = document.querySelector('.el-dialog')
    if (!d) return null
    const dragger = d.querySelector('.el-upload-dragger')
    return {
      hasDragger: !!dragger,
      isDrag: dragger ? dragger.classList.contains('el-upload-dragger') : false,
      text: dragger ? dragger.innerText : '',
      hasFileInput: !!d.querySelector('input[type=file]'),
      accept: d.querySelector('input[type=file]')?.accept || '',
    }
  })()`)
  check('工具: 弹窗内有拖拽上传区', drop && drop.hasDragger, JSON.stringify(drop))
  check(
    '工具: 拖拽区提示「拖到这里」',
    drop && drop.text.includes('拖到这里'),
    JSON.stringify(drop),
  )
  check('工具: 拖拽区只收 zip', drop && drop.accept === '.zip', JSON.stringify(drop))

  // 关掉弹窗(取消是文字按钮)
  await evalJs(c, `(() => {
    const dlg = document.querySelector('.el-dialog')
    if (!dlg) return false
    const btn = [...dlg.querySelectorAll('button')].find(b => b.textContent.trim() === '取消')
    if (btn) btn.click()
    return true
  })()`)
  await sleep(600)

  ws.close()
  await fetch(`${CDP}/json/close/${target.id}`)
}

// ---------- 4. 模型:新增提供商弹窗 ----------
{
  const target = await newTarget(`${BASE}/#/models`)
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r))
  const c = cdp(ws)
  await c.send('Runtime.enable')
  await sleep(2500)

  const clicked = await evalJs(c, CLICK_ICON('新增提供商'))
  await sleep(600)
  const dlg = await evalJs(c, `document.querySelector('.el-dialog')?.innerText || ''`)
  check('模型: 新增提供商弹窗打开', clicked && dlg.includes('Base URL'))

  // 弹窗里要有「提供商 ID」字段,标签全是中文
  const labels = await evalJs(c, `(() => {
    const d = document.querySelector('.el-dialog')
    if (!d) return []
    return [...d.querySelectorAll('.el-form-item__label')].map(l => l.innerText.trim())
  })()`)
  check('模型: 弹窗有「提供商 ID」字段', labels.includes('提供商 ID'), JSON.stringify(labels))
  check('模型: 字段名是中文', !labels.some((l) => /接口地址|API Key/i.test(l)), JSON.stringify(labels))
  // 四个字段都必填(带红色星号)
  const required = await evalJs(c, `(() => {
    const d = document.querySelector('.el-dialog')
    if (!d) return []
    return [...d.querySelectorAll('.el-form-item.is-required')].map(l => l.querySelector('.el-form-item__label')?.innerText.trim())
  })()`)
  check(
    '模型: 四个字段都标了必填',
    ['提供商名称', '提供商 ID', 'Base URL', 'API 密钥'].every((x) => required.includes(x)),
    JSON.stringify(required),
  )

  ws.close()
  await fetch(`${CDP}/json/close/${target.id}`)
}

// ---------- 5. 圆形图标按钮样式 ----------
{
  const target = await newTarget(`${BASE}/#/agents`)
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r))
  const c = cdp(ws)
  await c.send('Runtime.enable')
  await sleep(2500)

  const style = await evalJs(c, `(() => {
    const btn = document.querySelector('.icon-btn')
    if (!btn) return null
    const cs = getComputedStyle(btn)
    return {
      radius: cs.borderRadius,
      w: cs.width,
      h: cs.height,
      text: btn.innerText.trim(),
    }
  })()`)
  check('按钮: 有圆形图标按钮', !!style)
  check('按钮: 边框是圆形', style && style.radius.startsWith('50%'), JSON.stringify(style))
  check('按钮: 宽高一致(正圆)', style && style.w === style.h, JSON.stringify(style))
  check('按钮: 无文字', style && style.text === '', JSON.stringify(style))

  const biCount = await evalJs(c, `document.querySelectorAll('i.bi').length`)
  check('图标: 页面渲染 bootstrap 图标', biCount > 0, `count=${biCount}`)

  ws.close()
  await fetch(`${CDP}/json/close/${target.id}`)
}

// ---------- 6. 对话输入区:共用外框 + 底部图标行 ----------
{
  const target = await newTarget(`${BASE}/#/chat`)
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r))
  const c = cdp(ws)
  await c.send('Runtime.enable')
  await sleep(3000)

  const composer = await evalJs(c, `(() => {
    const box = document.querySelector('.composer-box')
    if (!box) return null
    const cs = getComputedStyle(box)
    const bar = box.querySelector('.composer-bar')
    const ta = box.querySelector('textarea')
    const barCs = bar ? getComputedStyle(bar) : null
    return {
      border: cs.borderTopWidth + ' ' + cs.borderTopStyle,
      radius: cs.borderRadius,
      barTopBorder: barCs ? barCs.borderTopWidth : null,
      taInBox: !!ta && box.contains(ta),
      barInBox: !!bar && box.contains(bar),
      btns: box.querySelectorAll('.icon-btn').length,
      btnTexts: [...box.querySelectorAll('.icon-btn')].map(b => b.innerText.trim()),
    }
  })()`)
  check('输入区: 存在共用外框', !!composer)
  check('输入区: 外框有边框', composer && composer.border.startsWith('1px'), JSON.stringify(composer))
  check('输入区: 外框是圆角', composer && composer.radius !== '0px')
  check('输入区: 输入框在外框内', composer && composer.taInBox)
  check('输入区: 图标行在外框内', composer && composer.barInBox)
  check('输入区: 底部有图标按钮', composer && composer.btns >= 4, JSON.stringify(composer))
  check(
    '输入区: 图标按钮无文字',
    composer && composer.btnTexts.every((x) => x === ''),
    JSON.stringify(composer),
  )

  // 图标行在输入框下方(同一外框里,bar 的 top 在 textarea 的 bottom 之下)
  const stacked = await evalJs(c, `(() => {
    const ta = document.querySelector('.composer-box textarea')
    const bar = document.querySelector('.composer-bar')
    if (!ta || !bar) return null
    const a = ta.getBoundingClientRect()
    const b = bar.getBoundingClientRect()
    return { taBottom: Math.round(a.bottom), barTop: Math.round(b.top) }
  })()`)
  check('输入区: 图标行在输入框下方', stacked && stacked.barTop >= stacked.taBottom, JSON.stringify(stacked))

  ws.close()
  await fetch(`${CDP}/json/close/${target.id}`)
}

console.log(failed ? `\n${failed} 项失败` : '\n交互流程全部正常')
process.exit(failed ? 1 : 0)
