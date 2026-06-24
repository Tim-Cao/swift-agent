// SSE 聊天:用 fetch + ReadableStream 解析后端 EventSourceResponse

/**
 * 流式发送消息
 * @param {{ session_id: string|null, message: string, agent_name?: string|null, upload_dir?: string|null }} payload
 * @param {{ onToken, onToolCall, onToolResult, onFile, onDone, onError }} handlers
 * @returns { AbortController }
 */
export function streamChat(payload, handlers = {}) {
  const controller = new AbortController()
  const { signal } = controller

  console.log('[SSE] streamChat called, keys:', Object.keys(payload || {}))

  fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
    .then(async (resp) => {
      console.log('[SSE] response', resp.status, resp.headers.get('content-type'))
      if (!resp.ok || !resp.body) {
        handlers.onError?.(new Error(`HTTP ${resp.status}`))
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      // buffer 统一存已 normalize 的字节(只含 \n,没有 \r)
      let buffer = ''
      let readCount = 0
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        readCount += 1
        // 把 TCP 流的字节 decode 出来,再做 \r\n / \r → \n 归一
        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
        if (readCount <= 3) {
          console.log('[SSE] read', readCount, 'bytes:', buffer.length, 'head:', JSON.stringify(buffer.slice(0, 250)))
        }

        // SSE 事件以 \n\n 分隔(SSE 规范)
        let idx
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const raw = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          const evt = parseSSEEvent(raw)
          if (!evt) continue
          console.log('[SSE] dispatch', evt.event, 'payload:', JSON.stringify(evt.payload).slice(0, 150))
          dispatch(evt, handlers)
        }
      }
      console.log('[SSE] stream end, total reads:', readCount, 'remaining buffer:', JSON.stringify(buffer))
      handlers.onDone?.({})
    })
    .catch((err) => {
      console.error('[SSE] fetch chain error:', err)
      if (err.name !== 'AbortError') handlers.onError?.(err)
    })

  return controller
}

function parseSSEEvent(raw) {
  let event = 'message'
  let data = ''
  for (const line of raw.split('\n')) {
    // SSE 规范:冒号后第一个空格不算 value 一部分;若没有冒号,跳过
    const colonIdx = line.indexOf(':')
    if (colonIdx < 0) continue
    const field = line.slice(0, colonIdx)
    let value = line.slice(colonIdx + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    else if (field === 'data') data += (data ? '\n' : '') + value
  }
  if (!data) return null
  let payload
  try {
    payload = JSON.parse(data)
  } catch {
    payload = { raw: data }
  }
  return { event, payload }
}

function dispatch({ event, payload }, handlers) {
  switch (event) {
    case 'token':
      handlers.onToken?.(payload.content ?? '')
      break
    case 'tool_call':
      handlers.onToolCall?.(payload)
      break
    case 'tool_result':
      handlers.onToolResult?.(payload)
      break
    case 'file':
      // Excel 等结果文件的下载事件:{ url, filename, mime, size_bytes }
      handlers.onFile?.(payload)
      break
    case 'done':
      console.log('[SSE] onDone fired')
      handlers.onDone?.(payload)
      break
    case 'error':
      console.log('[SSE] onError from server:', payload)
      handlers.onError?.(new Error(payload.content || payload.message || 'stream error'))
      break
    default:
      handlers.onToken?.(payload.content ?? '')
  }
}
