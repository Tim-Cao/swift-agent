<template>
  <div :class="['bubble', role]">
    <div class="role-label">{{ role === 'user' ? '我' : 'AI' }}</div>
    <div class="content">
      <template v-if="role === 'assistant'">
        <!-- 等待首个 token:content 为空且 pending,显示三点动画 -->
        <div
          v-if="pending && !content"
          class="typing-indicator"
          aria-label="AI 正在思考"
        >
          <span></span>
          <span></span>
          <span></span>
        </div>
        <MarkdownView v-else :content="content" />
      </template>
      <template v-else>
        <div v-if="content" class="text">{{ content }}</div>
      </template>

      <!-- 用户本轮上传的文件:文件卡放在气泡里(不是输入框上方) -->
      <div v-if="uploads.length" class="uploads">
        <div v-for="(f, idx) in uploads" :key="idx" class="upload-card">
          <i class="bi bi-file-earmark-zip file-icon"></i>
          <div class="file-info">
            <div class="file-name">{{ f.name }}</div>
            <div class="file-meta">
              {{ formatBytes(f.size_bytes) }}
              <span v-if="f.csv_count">· {{ f.csv_count }} 个 CSV</span>
            </div>
          </div>
        </div>
      </div>

      <!-- AI 产出的结果文件下载卡(xlsx / csv):fetch + Blob 保证浏览器触发下载
           而不是打开预览;按钮状态有 downloading / done / error 反馈 -->
      <div v-if="attachments && attachments.length" class="attachments">
        <div
          v-for="(att, idx) in attachments"
          :key="idx"
          :class="['file-card', `status-${att.status || 'idle'}`]"
        >
          <i class="bi bi-file-earmark file-icon"></i>
          <div class="file-info">
            <div class="file-name">{{ att.filename }}</div>
            <div class="file-meta">
              {{ formatBytes(att.size_bytes) }} ·
              <span v-if="att.status === 'downloading'">下载中…</span>
              <span v-else-if="att.status === 'done'">已下载</span>
              <span v-else-if="att.status === 'error'">下载失败</span>
              <span v-else>点击下载</span>
            </div>
          </div>
          <IconButton
            icon="bi-download"
            variant="primary"
            title="下载结果"
            :loading="att.status === 'downloading'"
            :disabled="att.status === 'downloading'"
            @click="downloadFile(att, idx)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ElMessage } from 'element-plus'
import IconButton from './IconButton.vue'
import MarkdownView from './MarkdownView.vue'

const props = defineProps({
  role: { type: String, required: true },
  content: { type: String, default: '' },
  pending: { type: Boolean, default: false },
  /**
   * attachments: [{ url, filename, mime, size_bytes, status? }]
   * status 由本组件写入('idle' | 'downloading' | 'done' | 'error'),
   * 父组件只需在收到 file 事件时 push 即可,不必管理 status。
   */
  attachments: { type: Array, default: () => [] },
  /**
   * uploads: 用户上传的文件 [{ name, size_bytes, csv_count }]
   * 只有用户消息才有(assistant 消息的产出文件走 attachments)。
   */
  uploads: { type: Array, default: () => [] },
})

// downloadFile 通过 fetch 拿 blob + a 标签触发下载,避免 target=_blank 打开预览
async function downloadFile(att, idx) {
  if (!att?.url) return
  att.status = 'downloading'
  try {
    const resp = await fetch(att.url, { method: 'GET' })
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status} ${resp.statusText}`)
    }
    const blob = await resp.blob()
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = att.filename || 'download'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    // 给浏览器一点时间真正发起下载再 revoke
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
    att.status = 'done'
    ElMessage.success(`${att.filename} 已开始下载`)
  } catch (e) {
    att.status = 'error'
    ElMessage.error(`下载失败:${e.message || e}`)
  }
}

function formatBytes(n) {
  if (!n && n !== 0) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}
</script>

<style scoped>
.bubble {
  margin: var(--n-gap-md) 0;
  display: flex;
  flex-direction: column;
}
.bubble .role-label {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  margin-bottom: var(--n-gap-xs);
}
.bubble.user {
  align-items: flex-end;
}
.bubble.user .content {
  background: var(--n-accent-bg);
  color: var(--n-text);
  padding: var(--n-gap-sm) var(--n-gap);
  border-radius: var(--n-radius-lg);
  max-width: 80%;
  display: flex;
  flex-direction: column;
  gap: var(--n-gap-sm);
}
.bubble.assistant .content {
  background: transparent;
  padding: 0;
  max-width: 100%;
  width: 100%;
}

/* 三点等待动画 */
.typing-indicator {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  height: 18px;
  padding: 2px 0;
}
.typing-indicator span {
  display: inline-block;
  width: 6px;
  height: 6px;
  background: var(--n-text-tertiary);
  border-radius: 50%;
  animation: typing-bounce 1.2s infinite ease-in-out both;
}
.typing-indicator span:nth-child(1) {
  animation-delay: 0s;
}
.typing-indicator span:nth-child(2) {
  animation-delay: 0.15s;
}
.typing-indicator span:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes typing-bounce {
  0%,
  60%,
  100% {
    opacity: 0.4;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-4px);
  }
}

/* 用户上传的文件卡 */
.uploads {
  display: flex;
  flex-direction: column;
  gap: var(--n-gap-xs);
}
.upload-card {
  display: flex;
  align-items: center;
  gap: var(--n-gap-sm);
  padding: var(--n-gap-sm) var(--n-gap);
  background: var(--n-bg-card);
  border: 1px solid var(--n-border);
  border-radius: var(--n-radius);
}

/* 结果文件下载卡 */
.attachments {
  display: flex;
  flex-direction: column;
  gap: var(--n-gap-sm);
  margin-top: var(--n-gap);
}
.file-card {
  display: flex;
  align-items: center;
  gap: var(--n-gap);
  padding: var(--n-gap) var(--n-gap);
  background: var(--n-bg-card);
  border: 1px solid var(--n-border);
  border-left: 3px solid var(--n-accent);
  border-radius: var(--n-radius);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.file-card:hover {
  border-color: var(--n-accent-border);
  box-shadow: var(--n-shadow);
}
.file-card.status-done {
  border-left-color: var(--n-green);
}
.file-card.status-error {
  border-left-color: var(--n-red);
}
.file-icon {
  font-size: 28px;
  color: var(--n-accent);
  flex-shrink: 0;
}
.file-info {
  flex: 1;
  min-width: 0;
}
.file-name {
  font-size: var(--n-text-sm);
  font-weight: 600;
  color: var(--n-text);
  word-break: break-all;
}
.file-meta {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  margin-top: 2px;
}
</style>
