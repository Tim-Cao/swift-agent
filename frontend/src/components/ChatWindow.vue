<template>
  <div class="chat-window">
    <div class="messages" ref="scrollRef">
      <div v-if="!messages.length" class="empty">开始一次对话吧 👋</div>
      <MessageBubble
        v-for="(m, i) in messages"
        :key="i"
        :role="m.role"
        :content="m.content"
        :attachments="m.attachments"
        :pending="isPending(i)"
      />
    </div>
    <InputBar
      ref="inputBarRef"
      :disabled="isStreaming"
      :session-id="sessionId"
      @send="onSend"
    />
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import MessageBubble from './MessageBubble.vue'
import InputBar from './InputBar.vue'
import { useChat } from '../stores/chat'
import { useSessionStore } from '../stores/session'

const props = defineProps({
  messages: { type: Array, required: true },
  sessionId: { type: String, default: null },
})
const emit = defineEmits(['appendMessage', 'updateSessionId'])

const scrollRef = ref(null)
const inputBarRef = ref(null)
const { isStreaming, send } = useChat()
const store = useSessionStore()

function scrollToBottom() {
  nextTick(() => {
    if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  })
}

watch(
  () => props.messages.length,
  () => scrollToBottom(),
)
// 流式期间,content 也会持续增长,需要跟着滚到底
watch(
  () => {
    const last = props.messages[props.messages.length - 1]
    return last && last.role === 'assistant' ? last.content : null
  },
  () => scrollToBottom(),
)

/**
 * 是否显示三点等待动画:仅"最后一条 assistant 消息 + 流式进行中 + 尚未收到首个 token"为 true。
 * 首个 token 到达后 m.content 不再为空,pending 自动转 false,动画被 MarkdownView 替换。
 */
function isPending(index) {
  const m = props.messages[index]
  if (!m || m.role !== 'assistant') return false
  if (index !== props.messages.length - 1) return false
  if (!isStreaming.value) return false
  if (m.content && m.content.length > 0) return false
  return true
}

async function onSend(payload) {
  // payload: { message, upload_dir }
  if (!props.sessionId) {
    emit('appendMessage', { role: 'system', content: '请先在左侧选择或新建会话' })
    return
  }
  // 用户消息 + 占位 assistant 消息都进 store(messages 是响应式 ref)
  store.pushMessage({ role: 'user', content: payload.message })
  store.pushMessage({ role: 'assistant', content: '', attachments: [] })

  await send(
    {
      session_id: props.sessionId,
      message: payload.message,
      upload_dir: payload.upload_dir || null,
    },
    {
      // 直接调 store 的响应式 action:每次 token 到来更新最后一条 assistant.content,
      // Vue 响应式系统自动触发 MessageBubble 重新渲染——字真的能"流式吐出来"。
      onToken: (t) => store.appendToken(t),
      onFile: (fileMeta) => {
        store.attachFile({
          url: fileMeta.url,
          filename: fileMeta.filename,
          mime: fileMeta.mime,
          size_bytes: fileMeta.size_bytes,
        })
      },
      onDone: () => {},
      onError: (e) => {
        store.appendToken(`\n\n[error] ${e.message}`)
      },
    },
  )
}
</script>

<style scoped>
.chat-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fafafa;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}
.empty {
  text-align: center;
  color: #aaa;
  margin-top: 60px;
}
</style>