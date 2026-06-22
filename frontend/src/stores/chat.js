import { ref } from 'vue'
import { streamChat } from '../api/chat'

const isStreaming = ref(false)
let controller = null

export function useChat() {
  async function send(
    payload,
    { onToken, onToolCall, onToolResult, onFile, onDone, onError } = {},
  ) {
    if (isStreaming.value) return
    isStreaming.value = true
    controller = streamChat(payload, {
      onToken: (t) => onToken?.(t),
      onToolCall: (p) => onToolCall?.(p),
      onToolResult: (p) => onToolResult?.(p),
      onFile: (p) => onFile?.(p),
      onDone: (meta) => {
        isStreaming.value = false
        onDone?.(meta)
      },
      onError: (e) => {
        isStreaming.value = false
        onError?.(e)
      },
    })
  }

  function abort() {
    controller?.abort()
    isStreaming.value = false
  }

  return { isStreaming, send, abort }
}
