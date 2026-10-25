// 智能体(agents)API
import http from './http'

/** 管理页:全部 agent(卡片展示草稿配置) */
export const listAgents = () => http.get('/agents').then((r) => r.data)

/** 市场:只返回已发布的 agent(卡片展示发布配置) */
export const listMarketAgents = () => http.get('/agents/market').then((r) => r.data)

export const getAgent = (id) => http.get(`/agents/${id}`).then((r) => r.data)

export const createAgent = (payload) =>
  http.post('/agents', payload).then((r) => r.data)

export const updateAgent = (id, payload) =>
  http.patch(`/agents/${id}`, payload).then((r) => r.data)

export const deleteAgent = (id) => http.delete(`/agents/${id}`).then((r) => r.data)

/** 设为默认 agent(会话未绑定时用它) */
export const setDefaultAgent = (id) =>
  http.post(`/agents/${id}/default`).then((r) => r.data)

/** 取消默认 agent */
export const unsetDefaultAgent = (id) =>
  http.delete(`/agents/${id}/default`).then((r) => r.data)
