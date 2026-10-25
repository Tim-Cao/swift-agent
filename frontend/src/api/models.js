// 模型(providers + models)API
import http from './http'

// ---- 提供商 ----

export const listProviders = () => http.get('/providers').then((r) => r.data)

export const createProvider = (payload) =>
  http.post('/providers', payload).then((r) => r.data)

export const updateProvider = (id, payload) =>
  http.patch(`/providers/${id}`, payload).then((r) => r.data)

export const deleteProvider = (id) =>
  http.delete(`/providers/${id}`).then((r) => r.data)

/** 通过提供商的 /models 接口发现可用模型 */
export const discoverModels = (providerId) =>
  http.post(`/providers/${providerId}/discover`).then((r) => r.data)

// ---- 模型 ----

export const listModels = () => http.get('/models').then((r) => r.data)

/** 设为默认模型 */
export const setDefaultModel = (modelId) =>
  http.post(`/models/${modelId}/default`).then((r) => r.data)

/** 取消默认模型 */
export const unsetDefaultModel = (modelId) =>
  http.delete(`/models/${modelId}/default`).then((r) => r.data)
