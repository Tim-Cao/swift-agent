// MCP 服务端管理 API
import http from './http'

/** 列出全部 MCP server */
export const listMcpServers = () => http.get('/mcp').then((r) => r.data)

export const createMcpServer = (payload) =>
  http.post('/mcp', payload).then((r) => r.data)

export const updateMcpServer = (id, payload) =>
  http.patch(`/mcp/${id}`, payload).then((r) => r.data)

export const deleteMcpServer = (id) =>
  http.delete(`/mcp/${id}`).then((r) => r.data)

/** 测试连接:连一下看能不能拿到工具 */
export const testMcpServer = (id) =>
  http.post(`/mcp/${id}/test`).then((r) => r.data)

/** 重新装载全部启用的 server(改了配置之后用) */
export const reloadMcpServers = () => http.post('/mcp/reload').then((r) => r.data)
