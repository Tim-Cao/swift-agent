// Trajectory + Session log API wrapper
import http from './http'

/**
 * 拉取会话的折叠轨迹。
 *
 * 返回结构(由后端 ``app.trajectory.schema.Trajectory`` 定义):
 * {
 *   session: { id, created_at, agent_name, model, ... },
 *   turns: [
 *     {
 *       turn, started_at, ended_at, ended_reason,
 *       user_message,
 *       steps: [
 *         { turn, step, kind: 'assistant_message'|'tool'|'file',
 *           started_at, ended_at, latency_ms,
 *           tool?: { call_id, name, input, output, is_error, latency_ms },
 *           assistant?: { content, input_tokens, output_tokens },
 *           file_meta?: { url, filename, mime, size_bytes } }
 *       ]
 *     }
 *   ],
 *   summary: {
 *     turns, steps,
 *     tool_calls: [{ name, count, error_count }],
 *     total_input_tokens, total_output_tokens,
 *     empty
 *   }
 * }
 */
export async function getTrajectory(sessionId) {
  const { data } = await http.get(`/sessions/${sessionId}/trajectory`)
  return data
}

/**
 * 触发浏览器下载会话的原始 JSONL 日志(``session-<id>.jsonl``)。
 *
 * 通过 ``window.location.href`` 走原生下载,避免 axios 把 blob
 * 留在内存里转 base64 的浪费。
 */
export function exportSessionLog(sessionId) {
  const url = `/api/sessions/${sessionId}/log/export`
  // 用 a 标签触发下载,避免当前页面被替换
  const a = document.createElement('a')
  a.href = url
  a.download = `session-${sessionId}.jsonl`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}