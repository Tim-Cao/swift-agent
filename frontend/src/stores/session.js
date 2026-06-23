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
  }

  async function newSession() {
    const s = await apiCreate({ title: '新会话' })
    sessions.value.unshift(s)
    currentId.value = s.id
    messages.value = []
    return s
  }

  async function selectSession(id) {
    currentId.value = id
    messages.value = await apiMessages(id)
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
