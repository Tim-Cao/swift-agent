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

  fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
    .then(async (resp) => {
      if (!resp.ok || !resp.body) {
        handlers.onError?.(new Error(`HTTP ${resp.status}`))
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE 事件以 \n\n 分隔,每条事件形如:event: <type>\ndata: <json>\n
        let idx
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const raw = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          const evt = parseSSEEvent(raw)
          if (!evt) continue
          dispatch(evt, handlers)
        }
      }
      handlers.onDone?.({})
    })
    .catch((err) => {
      if (err.name !== 'AbortError') handlers.onError?.(err)
    })

  return controller
}

function parseSSEEvent(raw) {
  let event = 'message'
  let data = ''
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
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
      handlers.onDone?.(payload)
      break
    case 'error':
      handlers.onError?.(new Error(payload.content || payload.message || 'stream error'))
      break
    default:
      handlers.onToken?.(payload.content ?? '')
  }
}
