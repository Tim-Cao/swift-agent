<template>
  <div class="chat-window">
    <div class="messages" ref="scrollRef">
      <div v-if="!localMessages.length" class="empty">开始一次对话吧 👋</div>
      <MessageBubble
        v-for="(m, i) in localMessages"
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
const emit = defineEmits(['appendMessage'])

const scrollRef = ref(null)
const inputBarRef = ref(null)
const { isStreaming, send } = useChat()

/**
 * 用本地 reactive ref 镜像 props.messages,流式 token 直接 mutate
 * 本地副本(响应式),不再依赖 store 的方法是否齐全——
 * 这样即便 HMR 缓存了旧 store,流式显示也不会因方法缺失而炸。
 */
const localMessages = ref([...props.messages])

watch(
  () => props.messages,
  (val) => {
    // 父组件切换会话/加载历史时,整体替换本地副本
    localMessages.value = [...val]
    scrollToBottom()
  },
  { deep: true },
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

function isPending(index) {
  const m = localMessages.value[index]
  if (!m || m.role !== 'assistant') return false
  if (index !== localMessages.value.length - 1) return false
  if (!isStreaming.value) return false
  if (m.content && m.content.length > 0) return false
  return true
}

function pushLocal(msg) {
  localMessages.value.push(msg)
}

function appendTokenLocal(text) {
  if (!text) return
  const last = localMessages.value[localMessages.value.length - 1]
  if (last && last.role === 'assistant') {
    last.content = (last.content || '') + text
  }
}

function attachFileLocal(fileMeta) {
  const last = localMessages.value[localMessages.value.length - 1]
  if (last && last.role === 'assistant') {
    if (!last.attachments) last.attachments = []
    last.attachments.push(fileMeta)
  }
}

async function onSend(payload) {
  if (!props.sessionId) {
    emit('appendMessage', { role: 'system', content: '请先在左侧选择或新建会话' })
    return
  }
  // 本地响应式 ref 立刻拿到用户消息 + 占位 assistant 消息,
  // 流式 token 直接 mutate 这个本地 ref——HMR / store 方法缺失不影响显示
  pushLocal({ role: 'user', content: payload.message })
  pushLocal({ role: 'assistant', content: '', attachments: [] })

  // 同步告诉父组件持久化用户消息(后端流结束后会自己 append 完整 assistant
  // 消息,这里只 emit user 避免重复)
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