import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  listSessions,
  createSession as apiCreate,
  deleteSession as apiDelete,
  renameSession as apiRename,
  listMessages as apiMessages,
  setSessionAgent as apiSetAgent,
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
    // v11.3:不再自动选中第一个会话 —— 首页是「新对话」页,
    // 自动选中会把上次的内容直接摊开,跟豆包 / DeepSeek 的落地页不一致。
    // 想看历史就点侧边栏的会话。
  }

  /** 回到「新对话」状态:清掉当前会话 */
  function resetCurrent() {
    currentId.value = null
    messages.value = []
  }

  async function newSession(extra = {}) {
    const s = await apiCreate({ title: '新会话', ...extra })
    sessions.value.unshift(s)
    currentId.value = s.id
    messages.value = []
    return s
  }

  /** 切换会话使用的 agent(agentId 传 null = 恢复默认 supervisor) */
  async function setAgent(id, agentId) {
    const updated = await apiSetAgent(id, agentId)
    const idx = sessions.value.findIndex((s) => s.id === id)
    if (idx !== -1) sessions.value[idx] = updated
    return updated
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
    // v8.14:后端把附件存进了 Message.meta_json,list_messages 已返回 meta。
    // MessageBubble 直接读 message.attachments,所以这里把 meta.attachments
    // 拍平到顶层,让刷新/前端重启后下载按钮仍能渲染出来。
    //
    // v11.1:meta.attachments 里有两种东西,按 filename / name 区分:
    //   - AI 产出的结果文件(有 filename)→ attachments
    //   - 用户上传的文件(有 name)→ uploads(渲染成气泡里的文件卡)
    messages.value = msgs.map((m) => {
      const raw = m.attachments || m.meta?.attachments || []
      const uploads = raw.filter((a) => a.name && !a.filename)
      const downloads = raw.filter((a) => a.filename)
      return { ...m, attachments: downloads, uploads }
    })
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
    resetCurrent,
    newSession,
    setAgent,
    selectSession,
    removeSession,
    rename,
    pushMessage,
    appendToken,
    attachFile,
  }
})
