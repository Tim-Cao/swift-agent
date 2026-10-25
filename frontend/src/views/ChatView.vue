<template>
  <!-- 没有指定会话 → 新对话页(豆包 / DeepSeek 那种落地页) -->
  <NewChatView v-if="!sessionId" />

  <!-- 指定了会话 → 普通对话视图 -->
  <div v-else class="chat-page">
    <div class="agent-bar">
      <span class="bar-label">使用智能体</span>
      <el-select
        :model-value="store.currentSession?.agent_id || ''"
        class="agent-select"
        placeholder="默认 supervisor"
        clearable
        @change="onAgentChange"
      >
        <el-option
          v-for="a in agents"
          :key="a.id"
          :label="a.name"
          :value="a.id"
        />
      </el-select>
    </div>
    <ChatWindow
      :messages="store.messages"
      :session-id="store.currentId"
      :reload-key="reloadKey"
      @appendMessage="appendLocal"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useSessionStore } from '../stores/session'
import NewChatView from './NewChatView.vue'
import ChatWindow from '../components/ChatWindow.vue'
import { listAgents } from '../api/agents'
import { useRoute } from '../router'

const store = useSessionStore()
const { path, query, navigate } = useRoute()
const agents = ref([])

/** URL 里的会话 id(/chat/:id);没有就是新对话页 */
const sessionId = computed(() => {
  const m = path.value.match(/^\/chat\/(.+)$/)
  return m ? m[1] : null
})

/**
 * 每次重新加载会话就 +1。
 *
 * 切会话时 store.currentId 可能是**同一个** id(新对话页发完消息跳过来时,
 * newSession 已经把 currentId 设成这个 id 了),ChatWindow 里 watch(sessionId)
 * 就不会触发 —— 靠这个计数器补一刀,强制它重新同步消息。
 */
const reloadKey = ref(0)

onMounted(async () => {
  try {
    agents.value = await listAgents()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载智能体失败')
  }
  // 从智能体市场点进来:?agent=<id> → 新建绑定该 agent 的会话,跳到该会话
  const wanted = query.value.agent
  if (wanted) {
    const s = await store.newSession({ agent_id: wanted })
    // 用掉这个 query,避免刷新重复建会话
    navigate(`/chat/${s.id}`, { replace: true })
  }
})

/** URL 变了(点侧边栏历史会话 / 新对话页发完消息跳过来)→ 加载那个会话 */
watch(
  sessionId,
  async (id) => {
    if (!id) {
      // 回到新对话页:清掉当前会话,避免上一个会话的消息还挂着
      store.resetCurrent()
      return
    }
    // 无条件重新加载:新对话页发完消息跳过来时,store.currentId 已经是这个 id
    // (newSession 设的),但 messages 还是空的 —— 消息在服务端,得拉回来。
    try {
      await store.selectSession(id)
      reloadKey.value += 1
    } catch (e) {
      ElMessage.error(e?.response?.data?.detail || '加载会话失败')
      navigate('/chat', { replace: true })
    }
  },
  { immediate: true },
)

async function onAgentChange(agentId) {
  if (!store.currentId) {
    await store.newSession()
  }
  try {
    await store.setAgent(store.currentId, agentId || null)
    ElMessage.success(agentId ? '已切换智能体' : '已恢复默认智能体')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '切换失败')
  }
}

function appendLocal(msg) {
  // 临时展示消息(后端最终会通过 list_messages 返回完整记录)
  store.pushMessage(msg)
}
</script>

<style scoped>
.chat-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.agent-bar {
  display: flex;
  align-items: center;
  gap: var(--n-gap-sm);
  padding: var(--n-gap-sm) var(--n-gap-lg);
  border-bottom: 1px solid var(--n-border-light);
  background: var(--n-bg);
  flex-shrink: 0;
}
.bar-label {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  flex-shrink: 0;
}
.agent-select {
  width: 220px;
}
</style>
