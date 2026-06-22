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
      <div v-else class="text">{{ content }}</div>
    </div>
  </div>
</template>

<script setup>
import MarkdownView from './MarkdownView.vue'
defineProps({
  role: { type: String, required: true },
  content: { type: String, default: '' },
  pending: { type: Boolean, default: false },
})
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
</style>