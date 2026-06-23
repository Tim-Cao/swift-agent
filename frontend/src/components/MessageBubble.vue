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

      <!-- 结果文件下载卡(xlsx / csv):fetch + Blob 保证浏览器触发下载
           而不是打开预览;按钮状态有 downloading / done / error 反馈 -->
      <div v-if="attachments && attachments.length" class="attachments">
        <div
          v-for="(att, idx) in attachments"
          :key="idx"
          :class="['file-card', `status-${att.status || 'idle'}`]"
        >
          <el-icon class="file-icon"><Document /></el-icon>
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
          <el-button
            type="primary"
            :loading="att.status === 'downloading'"
            :disabled="att.status === 'downloading'"
            @click="downloadFile(att, idx)"
            class="download-btn"
          >
            <el-icon><Download /></el-icon>
            <span>下载结果</span>
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Document, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
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
  margin: 12px 0;
  display: flex;
  flex-direction: column;
}
.bubble .role-label {
  font-size: 12px;
  color: #888;
  margin-bottom: 4px;
}
.bubble.user {
  align-items: flex-end;
}
.bubble.user .content {
  background: #409eff;
  color: #fff;
  padding: 8px 12px;
  border-radius: 8px;
  max-width: 80%;
}
.bubble.assistant .content {
  background: #f4f4f5;
  padding: 10px 14px;
  border-radius: 8px;
  max-width: 90%;
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
  background: #909399;
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
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

/* 结果文件下载卡 */
.attachments {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.file-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: #fff;
  border: 1px solid #e6e8eb;
  border-left: 4px solid #409eff;
  border-radius: 6px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.file-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.12);
}
.file-card.status-done {
  border-left-color: #67c23a;
}
.file-card.status-error {
  border-left-color: #f56c6c;
}
.file-icon {
  font-size: 32px;
  color: #409eff;
  flex-shrink: 0;
}
.file-info {
  flex: 1;
  min-width: 0;
}
.file-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  word-break: break-all;
}
.file-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}
.download-btn {
  flex-shrink: 0;
}
.download-btn :deep(.el-icon) {
  margin-right: 4px;
}
</style>
