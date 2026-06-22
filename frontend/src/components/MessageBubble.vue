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

      <!-- 附件下载卡(Excel / CSV 等结果文件) -->
      <div v-if="attachments && attachments.length" class="attachments">
        <a
          v-for="(att, idx) in attachments"
          :key="idx"
          :href="att.url"
          :download="att.filename"
          target="_blank"
          rel="noopener"
          class="file-card"
        >
          <el-icon class="file-icon"><Document /></el-icon>
          <div class="file-info">
            <div class="file-name">{{ att.filename }}</div>
            <div class="file-meta">{{ formatBytes(att.size_bytes) }} · 点击下载</div>
          </div>
          <el-icon class="download-icon"><Download /></el-icon>
        </a>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Document, Download } from '@element-plus/icons-vue'
import MarkdownView from './MarkdownView.vue'

defineProps({
  role: { type: String, required: true },
  content: { type: String, default: '' },
  pending: { type: Boolean, default: false },
  /**
   * attachments: [{ url, filename, mime, size_bytes }]
   */
  attachments: { type: Array, default: () => [] },
})

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

/* 附件下载卡片 */
.attachments {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
}
.file-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: #fff;
  border: 1px solid #e6e8eb;
  border-radius: 6px;
  text-decoration: none;
  color: inherit;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.file-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.12);
}
.file-icon {
  font-size: 28px;
  color: #409eff;
  flex-shrink: 0;
}
.file-info {
  flex: 1;
  min-width: 0;
}
.file-name {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  word-break: break-all;
}
.file-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}
.download-icon {
  color: #909399;
  flex-shrink: 0;
}
.file-card:hover .download-icon {
  color: #409eff;
}
</style>