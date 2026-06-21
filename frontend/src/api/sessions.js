import http from './http'

export const listSessions = () => http.get('/sessions').then((r) => r.data)

export const createSession = (payload = {}) =>
  http.post('/sessions', payload).then((r) => r.data)

export const renameSession = (id, title) =>
  http.patch(`/sessions/${id}`, { title }).then((r) => r.data)

export const deleteSession = (id) =>
  http.delete(`/sessions/${id}`).then((r) => r.data)

export const listMessages = (sessionId) =>
  http.get(`/sessions/${sessionId}/messages`).then((r) => r.data)
