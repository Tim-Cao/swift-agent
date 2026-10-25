<template>
  <el-dialog
    :model-value="visible"
    title="选择工具"
    width="560px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <div class="picker">
      <el-input
        v-model="keyword"
        placeholder="搜索工具名称或描述"
        clearable
        class="search"
      >
        <template #prefix>
          <i class="bi bi-search"></i>
        </template>
      </el-input>

      <el-checkbox-group v-model="selected" class="tool-list">
        <label
          v-for="t in filtered"
          :key="t.id"
          class="tool-item"
          :class="{ picked: selected.includes(t.id) }"
        >
          <el-checkbox :value="t.id" />
          <div class="tool-body">
            <span class="tool-name">{{ t.display_name || t.name }}</span>
            <span class="tool-desc">{{ t.description || t.name }}</span>
          </div>
          <el-tag v-if="t.builtin" size="small" type="info" effect="plain">
            内置
          </el-tag>
        </label>
      </el-checkbox-group>

      <p v-if="!filtered.length" class="empty">
        {{ tools.length ? '没有匹配的工具' : '还没有工具,去「工具管理」上传一个吧。' }}
      </p>
    </div>

    <template #footer>
      <span class="picked-count">已选 {{ selected.length }} 个</span>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" @click="confirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  tools: { type: Array, default: () => [] },
  /** 已选的工具 id(编辑页当前草稿里的绑定) */
  modelValue: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:visible', 'confirm'])

const keyword = ref('')
const selected = ref([])

watch(
  () => props.visible,
  (v) => {
    if (!v) return
    keyword.value = ''
    selected.value = [...(props.modelValue || [])]
  },
  { immediate: true },
)

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return props.tools
  return props.tools.filter((t) => {
    const name = (t.display_name || t.name || '').toLowerCase()
    const desc = (t.description || '').toLowerCase()
    const call = (t.name || '').toLowerCase()
    return name.includes(kw) || desc.includes(kw) || call.includes(kw)
  })
})

function confirm() {
  emit('confirm', [...selected.value])
  emit('update:visible', false)
}
</script>

<style scoped>
.picker {
  display: flex;
  flex-direction: column;
  gap: var(--n-gap-sm);
}
.search {
  margin-bottom: var(--n-gap-xs);
}
.tool-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 380px;
  overflow-y: auto;
}
.tool-item {
  display: flex;
  align-items: flex-start;
  gap: var(--n-gap-sm);
  padding: var(--n-gap-sm);
  border-radius: var(--n-radius);
  cursor: pointer;
  transition: background-color 0.1s ease;
}
.tool-item:hover {
  background: var(--n-bg-hover);
}
.tool-item.picked {
  background: var(--n-accent-bg);
}
.tool-item :deep(.el-checkbox) {
  height: auto;
  margin-right: 0;
  margin-top: 2px;
}
.tool-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.tool-name {
  font-size: var(--n-text-sm);
  color: var(--n-text);
  font-weight: 500;
}
.tool-desc {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty {
  margin: var(--n-gap-md) 0 0;
  text-align: center;
  font-size: var(--n-text-sm);
  color: var(--n-text-tertiary);
}
.picked-count {
  float: left;
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  line-height: 32px;
}
</style>
