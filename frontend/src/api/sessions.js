import http from './http'

export const listSessions = () => http.get('/sessions').then((r) => r.data)

/** 取单个会话(含 agent_id) */
export const getSession = (id) => http.get(`/sessions/${id}`).then((r) => r.data)

export const createSession = (payload = {}) =>
  http.post('/sessions', payload).then((r) => r.data)

export const renameSession = (id, title) =>
  http.patch(`/sessions/${id}`, { title }).then((r) => r.data)

/** 切换会话使用的 agent(传 null 恢复默认) */
export const setSessionAgent = (id, agentId) =>
  http.patch(`/sessions/${id}`, { agent_id: agentId }).then((r) => r.data)

export const deleteSession = (id) =>
  http.delete(`/sessions/${id}`).then((r) => r.data)

export const listMessages = (sessionId) =>
  http.get(`/sessions/${sessionId}/messages`).then((r) => r.data)
