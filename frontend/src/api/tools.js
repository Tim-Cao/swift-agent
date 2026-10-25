// 工具(tools)API
import http from './http'

export const listTools = () => http.get('/tools').then((r) => r.data)

export const createTool = (payload) => http.post('/tools', payload).then((r) => r.data)

export const updateTool = (id, payload) =>
  http.patch(`/tools/${id}`, payload).then((r) => r.data)

export const deleteTool = (id) => http.delete(`/tools/${id}`).then((r) => r.data)

/**
 * 上传 zip 工具包。
 * @param {File} file zip 文件
 * @param {Object} [opts]
 * @param {string} [opts.replace_tool_id] 替换某个已有工具的实现(工具名不变)
 * @param {string} [opts.display_name]    覆盖显示名
 * @param {string} [opts.description]     覆盖描述
 * @returns {Promise<Array>} 注册成功的工具列表
 */
export function uploadToolPackage(file, opts = {}) {
  const form = new FormData()
  form.append('file', file)
  if (opts.replace_tool_id) form.append('replace_tool_id', opts.replace_tool_id)
  if (opts.display_name) form.append('display_name', opts.display_name)
  if (opts.description != null) form.append('description', opts.description)
  return http
    .post('/tools/upload', form, {
      headers: { 'content-type': 'multipart/form-data' },
      timeout: 60000,
    })
    .then((r) => r.data)
}
