<template>
  <el-tooltip
    :content="title"
    placement="top"
    :disabled="!title"
    :show-after="300"
    effect="dark"
  >
    <button
      type="button"
      :class="['icon-btn', `icon-btn-${variant}`, { 'icon-btn-sm': small, 'icon-btn-loading': loading }]"
      :data-tip="title"
      :aria-label="title"
      :disabled="disabled || loading"
      @click="$emit('click', $event)"
    >
      <i v-if="loading" class="bi bi-arrow-repeat is-loading"></i>
      <i v-else class="bi" :class="icon"></i>
      <span v-if="label" class="icon-btn-label">{{ label }}</span>
    </button>
  </el-tooltip>
</template>

<script setup>
/**
 * 纯图标按钮(圆形)。
 *
 * 「新建 / 上传 / 删除 / 编辑」这类操作用不上长文字,圆形图标按钮更干净。
 * - 提示统一走 el-tooltip(全站统一的气泡样式),不用原生 title
 * - data-tip 保留提示文字,给端到端检查脚本当选择器用
 * - variant: primary(实心蓝) / default(描边) / danger(红) / ghost(无边框)
 * - label 存在时在图标右侧补一行小字(少数场景需要文字说明时用)
 */
defineProps({
  /** bootstrap-icons 类名,如 "bi-plus-lg" */
  icon: { type: String, required: true },
  /** tooltip 文本 / aria-label */
  title: { type: String, default: '' },
  /** 可选的文字说明(默认不显示) */
  label: { type: String, default: '' },
  variant: { type: String, default: 'default' },
  small: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

defineEmits(['click'])
</script>

<style scoped>
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 32px;
  height: 32px;
  padding: 0;
  border-radius: 50%;
  border: 1px solid var(--n-border);
  background: var(--n-bg-card);
  color: var(--n-text-secondary);
  cursor: pointer;
  font-size: 15px;
  line-height: 1;
  flex-shrink: 0;
  transition:
    background-color 0.12s ease,
    border-color 0.12s ease,
    color 0.12s ease;
}
.icon-btn:hover:not(:disabled) {
  background: var(--n-bg-hover);
  border-color: var(--n-border-strong);
  color: var(--n-text);
}
.icon-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.icon-btn:focus-visible {
  outline: 2px solid var(--n-accent);
  outline-offset: 2px;
}

.icon-btn-sm {
  width: 26px;
  height: 26px;
  font-size: 13px;
}

.icon-btn-primary {
  background: var(--n-accent);
  border-color: var(--n-accent);
  color: #fff;
}
.icon-btn-primary:hover:not(:disabled) {
  background: var(--n-accent-hover);
  border-color: var(--n-accent-hover);
  color: #fff;
}

.icon-btn-danger {
  color: var(--n-red);
}
.icon-btn-danger:hover:not(:disabled) {
  background: var(--n-red-bg);
  border-color: var(--n-red);
  color: var(--n-red);
}

.icon-btn-ghost {
  border-color: transparent;
  background: transparent;
}

.icon-btn-label {
  font-size: var(--n-text-xs);
  white-space: nowrap;
}
</style>
