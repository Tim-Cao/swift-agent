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
    <!-- 临时调试 overlay:把每个 token 直接拼到屏幕上,绕开所有 Vue 渲染逻辑。
         硬刷后:看到这里有字 = onToken 被调;看不到 = SSE 解析或回调链断。
         修好后会移除。 -->
    <div
      v-if="debugChunks.length"
      style="position:fixed;bottom:0;left:0;right:0;max-height:30vh;overflow:auto;background:rgba(0,0,0,0.85);color:#0f0;font-family:monospace;font-size:11px;padding:6px;z-index:9999;white-space:pre-wrap"
    >
      <div>debug tokens ({{ debugChunks.length }} chunks, last len {{ debugChunks.at(-1)?.length }}):</div>
      <div>{{ debugChunks.join('') }}</div>
    </div>
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
 * 流式消息列表:每个消息有稳定 id,流式期间用 immutable replace
 * (即"用新对象替换原对象")驱动 Vue 重渲染,避免直接 mutate reactive
 * 对象的属性时 HMR / 跨组件边界触发不到更新的边界问题。
 */
let _idSeq = 0
function nextId() {
  _idSeq += 1
  return `m_${Date.now()}_${_idSeq}`
}

const localMessages = ref([])
// 临时调试 buffer:记录每个 token,渲染在屏幕底部 overlay
const debugChunks = ref([])

// 父组件切会话 / 加载历史时整体替换
watch(
  () => props.messages,
  (val) => {
    localMessages.value = (val || []).map((m) => ({ ...m, id: m.id || nextId() }))
    scrollToBottom()
  },
  { immediate: true, deep: true },
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
  // 调试:在屏幕底部 overlay 显示,绕开 console / Vue 渲染
  debugChunks.value.push(text)
  console.log('[chat] onToken len', text.length, '→ total', updated.content.length)
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
  // 立刻 push 用户消息 + 占位 assistant
  pushLocal({ role: 'user', content: payload.message })
  pushLocal({ role: 'assistant', content: '', attachments: [] })

  // 同步告诉父组件持久化用户消息
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
