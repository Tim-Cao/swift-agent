/**
 * 客户端调用信息。
 *
 * 每次发消息都带一份「这条请求是从哪来的」的小快照:
 *   { kind: "user", rpcId: "<本次请求唯一 id>", clientTimeZone: "Asia/Shanghai" }
 *
 * 后端把它落在 user 消息的 meta.source 和 session log 的 user_message 事件里,
 * 轨迹视图的「来源」标签页直接展示这三个字段。
 */

/** 生成一个足够随机的 id(浏览器没有 uuid 依赖,用 crypto + 时间戳凑一个) */
function makeRpcId() {
  const c = globalThis.crypto
  if (c?.randomUUID) return c.randomUUID()
  if (c?.getRandomValues) {
    const buf = new Uint8Array(16)
    c.getRandomValues(buf)
    return Array.from(buf, (b) => b.toString(16).padStart(2, '0')).join('')
  }
  return `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`
}

/** 本机时区(拿不到就空字符串) */
function clientTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || ''
  } catch {
    return ''
  }
}

/** 构造本次请求的来源信息 */
export function buildSource() {
  return {
    kind: 'user',
    rpcId: makeRpcId(),
    clientTimeZone: clientTimeZone(),
  }
}
