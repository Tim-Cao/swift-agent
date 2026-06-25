<template>
  <div class="chat-window">
    <div class="messages" ref="scrollRef">
      <div v-if="!localMessages.length" class="empty">开始一次对话吧 👋</div>
      <MessageBubble
        v-for="m in localMessages"
        :key="m.id"
        :role="m.role"
        :content="m.content"
        :attachments="m.attachments"
        :pending="isPending(m)"
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
const emit = defineEmits(['appendMessage'])

const scrollRef = ref(null)
const inputBarRef = ref(null)
const { isStreaming, send } = useChat()

/**
 * 流式消息列表:本地 ref 是显示真相;store 仅用于持久化。
 *
 * 关键设计:localMessages 只在 sessionId **变化**时从父组件同步。
 * 父组件 store 自身在用户发消息后会变(因为我们 emit 了 appendMessage),
 * 如果用 deep watch 同步会**覆盖**我们正在流式累积的本地状态,导致 token
 * 全部丢失(用户看到的就是"任务结束才显示")。
 */
let _idSeq = 0
function nextId() {
  _idSeq += 1
  return `m_${Date.now()}_${_idSeq}`
}

const localMessages = ref([])

// 切会话时同步
watch(
  () => props.sessionId,
  () => {
    // 切到新会话 / 切回老会话:用父组件 store 的 messages 重新初始化
    localMessages.value = (props.messages || []).map((m) => ({
      ...m,
      id: m.id || nextId(),
    }))
    scrollToBottom()
  },
  { immediate: true },
)

function scrollToBottom() {
  nextTick(() => {
    if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  })
}

watch(
  () => localMessages.value.length,
  () => scrollToBottom(),
)
watch(
  () => {
    const last = localMessages.value[localMessages.value.length - 1]
    return last && last.role === 'assistant' ? last.content : null
  },
  () => scrollToBottom(),
)

function isPending(m) {
  if (!m || m.role !== 'assistant') return false
  if (m !== localMessages.value[localMessages.value.length - 1]) return false
  if (!isStreaming.value) return false
  if (m.content && m.content.length > 0) return false
  return true
}

function pushLocal(msg) {
  localMessages.value = [...localMessages.value, { id: nextId(), ...msg }]
}

function appendTokenLocal(text) {
  if (!text) return
  const arr = localMessages.value
  const last = arr[arr.length - 1]
  if (!last || last.role !== 'assistant') return
  // immutable replace:用全新对象替换最后一条,V diff 必触发 MessageBubble 重渲染
  const updated = {
    ...last,
    content: (last.content || '') + text,
  }
  localMessages.value = [...arr.slice(0, -1), updated]
}

function attachFileLocal(fileMeta) {
  const arr = localMessages.value
  const last = arr[arr.length - 1]
  if (!last || last.role !== 'assistant') return
  const attachments = [...(last.attachments || []), fileMeta]
  localMessages.value = [...arr.slice(0, -1), { ...last, attachments }]
}

async function onSend(payload) {
  if (!props.sessionId) {
    emit('appendMessage', { role: 'system', content: '请先在左侧选择或新建会话' })
    return
  }
  // 1. 本地立刻拿到用户消息 + 占位 assistant
  pushLocal({ role: 'user', content: payload.message })
  pushLocal({ role: 'assistant', content: '', attachments: [] })

  // 2. 同步告诉父组件持久化用户消息(后端流结束会自己 append 完整 assistant)
  emit('appendMessage', { role: 'user', content: payload.message })

  await send(
    {
      session_id: props.sessionId,
      message: payload.message,
      upload_dir: payload.upload_dir || null,
    },
    {
      onToken: (t) => appendTokenLocal(t),
      onFile: (fileMeta) => attachFileLocal(fileMeta),
      onDone: () => {},
      onError: (e) => {
        console.error('[chat stream error]', e)
        appendTokenLocal(`\n\n[error] ${e?.message || e}`)
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
