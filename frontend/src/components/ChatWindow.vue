<template>
  <div class="chat-window">
    <div class="chat-header">
      <div class="chat-header-title">
        <span class="title-text">会话工作区</span>
        <span v-if="props.sessionId" class="session-id" :title="props.sessionId">{{ props.sessionId }}</span>
      </div>
    </div>

    <!-- Tab 行:参考 deepseek-harness 的 ConversationSession tabs -->
    <div v-if="props.sessionId" class="tabs" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        role="tab"
        :aria-selected="activeView === tab.id"
        :class="['tab', { 'tab-active': activeView === tab.id }]"
        @click="setView(tab.id)"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 内容区:根据 activeView 切换 -->
    <div v-show="activeView === 'chat'" class="messages" ref="scrollRef">
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

    <div v-show="activeView === 'trajectory'" class="trajectory-pane">
      <TrajectoryView :session-id="props.sessionId" :active="activeView === 'trajectory'" />
    </div>

    <!-- 输入条只在 chat tab 下显示 -->
    <InputBar
      v-if="activeView === 'chat'"
      ref="inputBarRef"
      :disabled="isStreaming"
      :session-id="sessionId"
      @send="onSend"
    />
  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import MessageBubble from './MessageBubble.vue'
import InputBar from './InputBar.vue'
import TrajectoryView from './TrajectoryView.vue'
import { useChat } from '../stores/chat'

// Tab 配置(参考 deepseek-harness 的 conversation.view slot 投影;
// 后续若加新视图,只在这里 push 一项即可)
const tabs = [
  { id: 'chat', label: '对话' },
  { id: 'trajectory', label: '轨迹' },
]

// 每个 session 独立记录当前选中的 tab(参考 deepseek ChatStoreState.view)
// 用 Map 持久化,切回老会话保留之前选择
const sessionView = ref(new Map())

const activeView = computed(() => {
  if (!props.sessionId) return 'chat'
  return sessionView.value.get(props.sessionId) || 'chat'
})

function setView(id) {
  if (!props.sessionId) return
  sessionView.value.set(props.sessionId, id)
  // 触发响应式
  sessionView.value = new Map(sessionView.value)
}

const trajectoryOpen = ref(false)

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

// 切会话时同步消息
watch(
  () => props.sessionId,
  () => {
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
      enable_web_search: !!payload.enable_web_search,
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
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #e6e8eb;
  min-height: 40px;
}
.chat-header-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.title-text {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.session-id {
  font-size: 12px;
  color: #909399;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  user-select: all;
  word-break: break-all;
  max-width: 100%;
}

/* Tab strip —— 对齐 deepseek-harness ConversationRoot.module.css:
   text-only / 13px / 16px / weight 500 / 36px gap / 8px left padding /
   inactive = muted / active = 蓝色 + 2px 下划线 */
.tabs {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 36px;
  padding: 4px 16px 0 8px;
  background: #fff;
  border-bottom: 1px solid #e6e8eb;
}
.tab {
  position: relative;
  padding: 0 0 11px;
  border: none;
  background: transparent;
  font-size: 13px;
  line-height: 16px;
  font-weight: 500;
  color: #909399;
  cursor: pointer;
  font-family: inherit;
}
.tab:hover {
  color: #606266;
}
.tab::after {
  content: '';
  position: absolute;
  right: 0;
  bottom: 1px;
  left: 0;
  height: 2px;
  border-radius: 2px;
  background: transparent;
}
.tab-active {
  color: #409eff;
}
.tab-active::after {
  background: #409eff;
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

/* 轨迹 tab 的内容区:沿用 messages 的滚动与边距,但 padding 稍小 */
.trajectory-pane {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}
</style>