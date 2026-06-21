<template>
  <div class="input-bar">
    <el-input
      v-model="text"
      type="textarea"
      :rows="3"
      placeholder="输入消息,Enter 发送,Shift+Enter 换行"
      :disabled="disabled"
      @keydown.enter.exact.prevent="submit"
    />
    <el-button
      type="primary"
      :loading="disabled"
      :disabled="!text.trim() || disabled"
      @click="submit"
    >
      {{ disabled ? '生成中…' : '发送' }}
    </el-button>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({ disabled: { type: Boolean, default: false } })
const emit = defineEmits(['send'])
const text = ref('')

function submit() {
  const t = text.value.trim()
  if (!t || props.disabled) return
  emit('send', t)
  text.value = ''
}
</script>

<style scoped>
.input-bar {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 12px;
  border-top: 1px solid #eee;
  background: #fff;
}
</style>
