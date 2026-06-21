<template>
  <div class="chat-window">
    <div class="messages" ref="scrollRef">
      <div v-if="!messages.length" class="empty">开始一次对话吧 👋</div>
      <MessageBubble
        v-for="(m, i) in messages"
        :key="i"
        :role="m.role"
        :content="m.content"
      />
    </div>
    <InputBar :disabled="isStreaming" @send="onSend" />
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
const emit = defineEmits(['appendMessage'])

const scrollRef = ref(null)
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

async function onSend(text) {
  if (!props.sessionId) {
    emit('appendMessage', { role: 'system', content: '请先在左侧选择或新建会话' })
    return
  }
  emit('appendMessage', { role: 'user', content: text })
  currentAssistant = { role: 'assistant', content: '' }
  emit('appendMessage', currentAssistant)

  await send(
    { session_id: props.sessionId, message: text },
    {
      onToken: (t) => {
        if (currentAssistant) currentAssistant.content += t
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
