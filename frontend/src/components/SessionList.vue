<template>
  <div class="session-list">
    <div class="header">
      <span>会话</span>
      <el-button size="small" type="primary" @click="$emit('new')">+ 新建</el-button>
    </div>
    <ul>
      <li
        v-for="s in sessions"
        :key="s.id"
        :class="{ active: s.id === currentId }"
        @click="$emit('select', s.id)"
      >
        <span class="title">{{ s.title }}</span>
        <el-button
          link
          size="small"
          type="danger"
          @click.stop="$emit('remove', s.id)"
        >×</el-button>
      </li>
      <li v-if="!sessions.length" class="empty">暂无会话</li>
    </ul>
  </div>
</template>

<script setup>
defineProps({
  sessions: { type: Array, required: true },
  currentId: { type: String, default: null },
})
defineEmits(['select', 'remove', 'new'])
</script>

<style scoped>
.session-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f7fa;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  font-weight: 600;
  border-bottom: 1px solid #e6e8eb;
}
ul {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  flex: 1;
}
li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid #eef0f3;
}
li:hover { background: #eef2f7; }
li.active { background: #d6e4ff; }
.title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { color: #999; text-align: center; padding: 20px; }
</style>
