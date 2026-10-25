<template>
  <div class="new-chat">
    <div class="new-chat-inner">
      <!-- 有消息了 → 变成普通对话视图(去掉 hero 和选择器) -->
      <template v-if="!messages.length">
        <div class="hero">
          <h1 class="hero-title">有什么可以帮你的?</h1>
          <p class="hero-sub">选一个智能体,或者直接开始对话。</p>
        </div>

        <!-- 智能体选择 -->
        <div class="picker">
          <div class="picker-label">选择智能体</div>
          <div class="picker-row">
            <!-- 默认(不绑定具体 agent) -->
            <button
              type="button"
              class="agent-chip"
              :class="{ active: !pickedAgentId }"
              @click="pickAgent('')"
            >
              <i class="bi bi-stars chip-icon"></i>
              <span class="chip-name">默认</span>
            </button>

            <button
              v-for="a in agents"
              :key="a.id"
              type="button"
              class="agent-chip"
              :class="{ active: pickedAgentId === a.id }"
              @click="pickAgent(a.id)"
            >
              <i class="bi bi-robot chip-icon"></i>
              <span class="chip-name">{{ a.name }}</span>
            </button>

            <span v-if="!agents.length && loading" class="picker-empty">
              正在加载智能体…
            </span>
          </div>
        </div>
      </template>

      <!-- 消息区(发第一条之后才出现) -->
      <div v-if="messages.length" class="messages">
        <MessageBubble
          v-for="m in messages"
          :key="m.id"
          :role="m.role"
          :content="m.content"
          :attachments="m.attachments"
          :uploads="m.uploads"
          :pending="isPending(m)"
        />
      </div>

      <!-- 输入区(跟已有对话页共用同一套组件) -->
      <div class="composer-wrap">
        <InputBar
          ref="inputBarRef"
          :session-id="sessionId"
          :ensure-session="ensureSession"
          :disabled="isStreaming"
          @send="onSend"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import InputBar from '../components/InputBar.vue'
import MessageBubble from '../components/MessageBubble.vue'
import { listAgents } from '../api/agents'
import { useChat } from '../stores/chat'
import { useSessionStore } from '../stores/session'
import { useRoute } from '../router'
import { buildSource } from '../utils/request'

const store = useSessionStore()
const { navigate } = useRoute()
const { isStreaming, send } = useChat()

const agents = ref([])
const loading = ref(true)
const pickedAgentId = ref('')
const sessionId = ref(null)
const messages = ref([])
/** 组件是否已被卸载(流式回调里用来判断还能不能 navigate) */
let unmounted = false

let _idSeq = 0
function nextId() {
  _idSeq += 1
  return `m_${Date.now()}_${_idSeq}`
}

onMounted(async () => {
  try {
    agents.value = await listAgents()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载智能体失败')
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  unmounted = true
  // 一条消息都没发 → 把占位会话删掉,免得历史列表里堆一排"新会话"
  if (sessionId.value && !messages.value.length) {
    store.removeSession(sessionId.value).catch(() => {})
  }
})

/** 选智能体 → 同步到当前会话(会话还没建就先记着) */
async function pickAgent(agentId) {
  pickedAgentId.value = agentId
  if (sessionId.value) {
    try {
      await store.setAgent(sessionId.value, agentId || null)
    } catch {
      /* 失败不挡聊天 */
    }
  }
}

/** 确保会话已建(发第一条消息 / 上传文件之前) */
async function ensureSession() {
  if (sessionId.value) return sessionId.value
  const s = await store.newSession(
    pickedAgentId.value ? { agent_id: pickedAgentId.value } : {},
  )
  sessionId.value = s.id
  return s.id
}

function isPending(m) {
  if (!m || m.role !== 'assistant') return false
  if (m !== messages.value[messages.value.length - 1]) return false
  if (!isStreaming.value) return false
  if (m.content && m.content.length > 0) return false
  return true
}

function pushLocal(msg) {
  messages.value = [...messages.value, { id: nextId(), ...msg }]
}

function appendTokenLocal(text) {
  if (!text) return
  const arr = messages.value
  const last = arr[arr.length - 1]
  if (!last || last.role !== 'assistant') return
  messages.value = [...arr.slice(0, -1), { ...last, content: (last.content || '') + text }]
}

function attachFileLocal(fileMeta) {
  const arr = messages.value
  const last = arr[arr.length - 1]
  if (!last || last.role !== 'assistant') return
  const attachments = [...(last.attachments || []), fileMeta]
  messages.value = [...arr.slice(0, -1), { ...last, attachments }]
}

/** 发送第一条消息 → 建会话 → 流式对话 → 结束后落到 /chat/:id */
async function onSend(payload) {
  try {
    await ensureSession()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '创建会话失败')
    return
  }

  pushLocal({
    role: 'user',
    content: payload.message,
    uploads: payload.attachment ? [payload.attachment] : [],
  })
  pushLocal({ role: 'assistant', content: '', attachments: [] })

  await send(
    {
      session_id: sessionId.value,
      message: payload.message,
      upload_dir: payload.upload_dir || null,
      attachment: payload.attachment || null,
      enable_web_search: !!payload.enable_web_search,
      // 客户端调用信息 —— 轨迹视图「来源」标签页展示
      source: buildSource(),
    },
    {
      onToken: (t) => appendTokenLocal(t),
      onFile: (fileMeta) => attachFileLocal(fileMeta),
      onDone: () => {
        // 这一轮结束后跳到会话页 —— 历史都在后端,刷新也不丢。
        // 必须在流**结束**后再跳:中途跳走会打断流式输出。
        if (!unmounted) navigate(`/chat/${sessionId.value}`)
      },
      onError: (e) => {
        console.error('[chat stream error]', e)
        appendTokenLocal(`\n\n[error] ${e?.message || e}`)
        if (!unmounted) navigate(`/chat/${sessionId.value}`)
      },
    },
  )
}

defineExpose({ ensureSession })
</script>

<style scoped>
.new-chat {
  height: 100%;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--n-gap-xl) var(--n-gap-lg);
  background: var(--n-bg);
}

.new-chat-inner {
  width: 100%;
  max-width: 760px;
  display: flex;
  flex-direction: column;
  gap: var(--n-gap-lg);
  /* 整体略微偏上,输入区在视觉重心附近 */
  margin-bottom: 8vh;
}

/* ---- 标题 ---- */
.hero {
  text-align: center;
}
.hero-title {
  margin: 0 0 var(--n-gap-sm);
  font-size: var(--n-text-2xl);
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--n-text);
}
.hero-sub {
  margin: 0;
  font-size: var(--n-text-sm);
  color: var(--n-text-tertiary);
}

/* ---- 智能体选择 ---- */
.picker-label {
  font-size: var(--n-text-xs);
  font-weight: 600;
  color: var(--n-text-tertiary);
  letter-spacing: 0.02em;
  margin-bottom: var(--n-gap-sm);
  text-align: center;
}
.picker-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--n-gap-sm);
}
.picker-empty {
  font-size: var(--n-text-sm);
  color: var(--n-text-tertiary);
}

.agent-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--n-border);
  border-radius: 999px;
  background: var(--n-bg-card);
  color: var(--n-text-secondary);
  font-family: inherit;
  font-size: var(--n-text-sm);
  cursor: pointer;
  transition:
    background-color 0.12s ease,
    border-color 0.12s ease,
    color 0.12s ease;
}
.agent-chip:hover {
  border-color: var(--n-border-strong);
  color: var(--n-text);
}
.agent-chip.active {
  background: var(--n-accent-bg);
  border-color: var(--n-accent-border);
  color: var(--n-accent);
  font-weight: 500;
}
.chip-icon {
  font-size: 13px;
  opacity: 0.8;
}
.chip-name {
  white-space: nowrap;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ---- 消息区 ---- */
.messages {
  display: flex;
  flex-direction: column;
  gap: var(--n-gap-md);
}

/* ---- 输入区 ---- */
.composer-wrap {
  width: 100%;
}
.composer-wrap :deep(.composer) {
  padding: 0;
  border-top: none;
  background: transparent;
}
</style>
