<template>
  <el-select
    :model-value="modelValue"
    class="agent-select"
    :loading="loading"
    :disabled="disabled"
    placeholder="选择智能体"
    @update:model-value="onSelect"
  >
    <el-option v-for="a in agents" :key="a.id" :value="a.id" :label="a.name">
      <span class="agent-opt">
        <i class="bi bi-robot agent-opt-icon"></i>
        <span class="agent-opt-name">{{ a.name }}</span>
      </span>
    </el-option>
  </el-select>
</template>

<script setup>
/**
 * 智能体选择框(紧凑版)。
 *
 * 放在输入框右下角、发送按钮旁边。原先新对话页有一排 chip,占地方又抢视线,
 * 收进输入框后跟发送操作在同一个视觉区域里。
 */
const props = defineProps({
  /** 当前选中的 agent id */
  modelValue: { type: String, default: '' },
  /** agent 列表 */
  agents: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

/** 选了哪个 agent(直接是真实 agent id) */
function onSelect(v) {
  emit('update:modelValue', v)
}
</script>

<style scoped>
.agent-select {
  width: 150px;
}

/* 高度跟旁边的圆形图标按钮(32px)对齐 */
.agent-select :deep(.el-select__wrapper) {
  min-height: 32px;
  padding: 0 28px 0 10px;
  font-size: var(--n-text-sm);
}

/* 下拉项:图标 + 名称 */
.agent-opt {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.agent-opt-icon {
  font-size: 13px;
  opacity: 0.75;
}
.agent-opt-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
