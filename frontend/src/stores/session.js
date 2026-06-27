import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  listSessions,
  createSession as apiCreate,
  deleteSession as apiDelete,
  renameSession as apiRename,
  listMessages as apiMessages,
} from '../api/sessions'

export const useSessionStore = defineStore('session', () => {
  const sessions = ref([])
  const currentId = ref(null)
  const messages = ref([])

  const currentSession = computed(() =>
    sessions.value.find((s) => s.id === currentId.value) || null,
  )

  async function loadSessions() {
    sessions.value = await listSessions()
    // v8.13:刷新页面时,如果有历史会话且当前没有选中,默认选中第一个,
    // 这样刷新后能直接看到上次的对话内容(否则 messages 是空的,
    // 用户会以为刷新把历史"清空"了)。
    if (!currentId.value && sessions.value.length > 0) {
      await selectSession(sessions.value[0].id)
    }
  }

  async function newSession() {
    const s = await apiCreate({ title: '新会话' })
    sessions.value.unshift(s)
    currentId.value = s.id
    messages.value = []
    return s
  }

  async function selectSession(id) {
    // v8.13:必须**先** await messages 再 set currentId。
    // ChatWindow 的 watcher 是 watch(() => props.sessionId),依赖
    // sessionId 变化触发 localMessages 同步。如果先 set currentId
    // 再 await messages,await 让出主线程后 watcher 立即触发,此时
    // props.messages 还是旧值([])→ localMessages 同步成空数组 →
    // 后续 messages 更新没人 watch → 窗口空白。
    // 反过来:先 await 让 messages 就位,再 set currentId 触发
    // watcher 时读到的就是新 messages,localMessages 正确填充。
    const msgs = await apiMessages(id)
    messages.value = msgs
    currentId.value = id
  }

  async function removeSession(id) {
    await apiDelete(id)
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (currentId.value === id) {
      currentId.value = null
      messages.value = []
    }
  }

  async function rename(id, title) {
    const updated = await apiRename(id, title)
    const idx = sessions.value.findIndex((s) => s.id === id)
    if (idx !== -1) sessions.value[idx] = updated
    return updated
  }

  function pushMessage(msg) {
    messages.value.push(msg)
  }

  /**
   * 流式追加:每次 token 到达时,更新最后一条 assistant 消息的 content
   * (以及必要时 append attachments)。直接操作 messages.value[-1] 会触发
   * 响应式,带动 MessageBubble 重新渲染。
   */
  function appendToken(text) {
    if (!text) return
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content = (last.content || '') + text
    }
  }

  function attachFile(fileMeta) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      if (!last.attachments) last.attachments = []
      last.attachments.push(fileMeta)
    }
  }

  return {
    sessions,
    currentId,
    messages,
    currentSession,
    loadSessions,
    newSession,
    selectSession,
    removeSession,
    rename,
    pushMessage,
    appendToken,
    attachFile,
  }
})
