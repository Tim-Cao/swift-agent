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

const props = defineProps({
  messages: { type: Array, required: true },
  sessionId: { type: String, default: null },
})
const emit = defineEmits(['appendMessage', 'updateSessionId'])

const scrollRef = ref(null)
const inputBarRef = ref(null)
const { isStreaming, send } = useChat()

let currentAssistant = null

function scrollToBottom() {
  nextTick(() => {
    if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  })
}

watch(
  () => props.messages.length,
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
  emit('appendMessage', { role: 'user', content: payload.message })
  currentAssistant = {
    role: 'assistant',
    content: '',
    attachments: [],
  }
  emit('appendMessage', currentAssistant)

  await send(
    {
      session_id: props.sessionId,
      message: payload.message,
      upload_dir: payload.upload_dir || null,
    },
    {
      onToken: (t) => {
        if (currentAssistant) currentAssistant.content += t
      },
      onFile: (fileMeta) => {
        // 后端在 ExcelWriterAgent 完成时推送的 file 事件
        if (currentAssistant) {
          if (!currentAssistant.attachments) currentAssistant.attachments = []
          currentAssistant.attachments.push({
            url: fileMeta.url,
            filename: fileMeta.filename,
            mime: fileMeta.mime,
            size_bytes: fileMeta.size_bytes,
          })
        }
      },
      onDone: () => {
        currentAssistant = null
      },
      onError: (e) => {
        if (currentAssistant) currentAssistant.content += `\n\n[error] ${e.message}`
        currentAssistant = null
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