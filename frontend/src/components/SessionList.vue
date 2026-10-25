<template>
  <div class="session-list">
    <ul>
      <li
        v-for="s in sessions"
        :key="s.id"
        :class="{ active: s.id === currentId }"
        @click="$emit('select', s.id)"
      >
        <i class="bi bi-chat-left-text item-icon"></i>
        <el-tooltip :content="s.title" placement="right" effect="dark">
          <span class="title">{{ s.title }}</span>
        </el-tooltip>
        <IconButton
          small
          variant="ghost"
          icon="bi-x-lg"
          title="删除会话"
          @click.stop="$emit('remove', s.id)"
        />
      </li>
      <li v-if="!sessions.length" class="empty">暂无历史会话</li>
    </ul>
  </div>
</template>

<script setup>
import IconButton from './IconButton.vue'

defineProps({
  sessions: { type: Array, required: true },
  currentId: { type: String, default: null },
})
defineEmits(['select', 'remove'])
</script>

<style scoped>
.session-list {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--n-bg-sidebar);
}
ul {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
li {
  display: flex;
  align-items: center;
  gap: var(--n-gap-xs);
  padding: 5px var(--n-gap-sm) 5px var(--n-gap);
  cursor: pointer;
  font-size: var(--n-text-sm);
  color: var(--n-text-secondary);
  border-radius: var(--n-radius-sm);
  margin: 0 var(--n-gap-xs);
  transition: background-color 0.1s ease, color 0.1s ease;
}
li:hover {
  background: var(--n-bg-hover);
  color: var(--n-text);
}
li.active {
  background: var(--n-bg-active);
  color: var(--n-text);
  font-weight: 500;
}
.item-icon {
  font-size: 12px;
  opacity: 0.5;
  flex-shrink: 0;
}
.title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty {
  color: var(--n-text-tertiary);
  text-align: center;
  padding: var(--n-gap) var(--n-gap-sm);
  font-size: var(--n-text-xs);
  cursor: default;
}
.empty:hover {
  background: transparent;
  color: var(--n-text-tertiary);
}
</style>
