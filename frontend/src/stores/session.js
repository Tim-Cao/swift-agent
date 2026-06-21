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
  }
})
