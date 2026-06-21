<template>
  <div :class="['bubble', role]">
    <div class="role-label">{{ role === 'user' ? '我' : 'AI' }}</div>
    <div class="content">
      <MarkdownView v-if="role === 'assistant'" :content="content" />
      <div v-else class="text">{{ content }}</div>
    </div>
  </div>
</template>

<script setup>
import MarkdownView from './MarkdownView.vue'
defineProps({
  role: { type: String, required: true },
  content: { type: String, default: '' },
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
</style>
