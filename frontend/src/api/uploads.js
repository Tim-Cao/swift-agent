import http from './http'

/**
 * 上传 zip 压缩包,后端解压到 /tmp/swift-agent/<session_id>/,返回 CSV 目录路径
 * @param {File} file
 * @param {string} [sessionId]
 * @returns {Promise<{
 *   session_id: string,
 *   upload_dir: string,
 *   csv_files: string[],
 *   zip_path: string,
 *   size_bytes: number,
 *   skipped_unsafe: string[],
 * }>}
 */
export function uploadZip(file, sessionId) {
  const form = new FormData()
  form.append('file', file)
  if (sessionId) form.append('session_id', sessionId)
  return http
    .post('/uploads', form, {
      headers: { 'content-type': 'multipart/form-data' },
      timeout: 120000, // 解压可能耗时
    })
    .then((r) => r.data)
}

/**
 * 把 /tmp/<session_id>/<name> 路径转成可下载的相对 URL
 */
export function downloadUrl(sessionId, filename) {
  return `/api/downloads/${sessionId}/${encodeURIComponent(filename)}`
}