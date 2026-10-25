<template>
  <div class="card-grid">
    <div v-if="!items.length" class="empty">
      <slot name="empty">
        <span class="empty-text">{{ emptyText }}</span>
      </slot>
    </div>
    <article
      v-for="item in items"
      :key="keyOf(item)"
      class="card"
      :class="{ 'card-readonly': readonly }"
      @click="onSelect(item)"
    >
      <header class="card-head">
        <!-- 类型图标:占两行 -->
        <div v-if="$slots.icon" class="card-icon">
          <slot name="icon" :item="item" />
        </div>

        <div class="card-head-main">
          <!-- 第一行:状态 -->
          <div class="card-row-top">
            <div class="card-status">
              <slot name="status" :item="item" />
            </div>
            <div class="card-actions" @click.stop>
              <slot name="actions" :item="item" />
            </div>
          </div>

          <!-- 第二行:名称 -->
          <div class="card-title-row">
            <h3 class="card-title">{{ titleOf(item) }}</h3>
            <slot name="tags" :item="item" />
          </div>
        </div>
      </header>

      <p class="card-desc">{{ descOf(item) }}</p>

      <footer v-if="$slots.footer" class="card-foot">
        <slot name="footer" :item="item" />
      </footer>
    </article>
  </div>
</template>

<script setup>
/**
 * 通用三列卡片网格(Notion 风格)。
 *
 * 列表页(智能体市场 / 智能体管理 / 工具管理 / 模型管理 / MCP 管理)共用
 * 这个组件。卡片头部是「类型图标 + 右侧两行」:
 *   - 左边:类型图标(占两行,slot 名 icon)
 *   - 右上:状态(slot 名 status)
 *   - 右下:名称(titleOf)
 */
const props = defineProps({
  items: { type: Array, default: () => [] },
  emptyText: { type: String, default: '暂无内容' },
  readonly: { type: Boolean, default: false },
  // 字段适配器:从 item 里取展示字段
  titleKey: { type: String, default: 'name' },
  descKey: { type: String, default: 'description' },
  titleOf: { type: Function, default: null },
  descOf: { type: Function, default: null },
  keyOf: { type: Function, default: null },
})

const emit = defineEmits(['select'])

function titleOf(item) {
  if (props.titleOf) return props.titleOf(item)
  return item[props.titleKey] || '(未命名)'
}
function descOf(item) {
  if (props.descOf) return props.descOf(item)
  return item[props.descKey] || '暂无描述'
}
function keyOf(item) {
  return props.keyOf ? props.keyOf(item) : item.id ?? item.name
}
function onSelect(item) {
  if (props.readonly) return
  emit('select', item)
}
</script>

<style scoped>
.card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--n-gap-md);
}

@media (max-width: 1100px) {
  .card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 720px) {
  .card-grid {
    grid-template-columns: 1fr;
  }
}

.card {
  display: flex;
  flex-direction: column;
  gap: var(--n-gap-sm);
  padding: var(--n-gap-md);
  background: var(--n-bg-card);
  border: 1px solid var(--n-border);
  border-radius: var(--n-radius-lg);
  cursor: pointer;
  transition:
    border-color 0.12s ease,
    box-shadow 0.12s ease,
    transform 0.12s ease;
  min-height: 148px;
}

.card:hover {
  border-color: var(--n-border-strong);
  box-shadow: var(--n-shadow);
}

.card-readonly {
  cursor: default;
}

.card-head {
  display: flex;
  align-items: stretch;
  gap: var(--n-gap-sm);
}

/* 类型图标:占两行(高度撑满头部) */
.card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  min-height: 44px;
  flex-shrink: 0;
  border-radius: var(--n-radius);
  background: var(--n-bg-subtle);
  color: var(--n-text-secondary);
  font-size: 17px;
}

.card-head-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  justify-content: center;
}

/* 第一行:状态 + 操作按钮 */
.card-row-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--n-gap-sm);
  min-height: 22px;
}

.card-status {
  display: flex;
  align-items: center;
  gap: var(--n-gap-xs);
  min-width: 0;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: var(--n-gap-xs);
  flex-shrink: 0;
}

/* 第二行:名称 + 标签 */
.card-title-row {
  display: flex;
  align-items: center;
  gap: var(--n-gap-xs);
  flex-wrap: wrap;
  min-width: 0;
}

.card-title {
  font-size: var(--n-text-md);
  font-weight: 600;
  margin: 0;
  letter-spacing: -0.01em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  margin: 0;
  font-size: var(--n-text-sm);
  color: var(--n-text-secondary);
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  flex: 1;
}

.card-foot {
  display: flex;
  align-items: center;
  gap: var(--n-gap-sm);
  flex-wrap: wrap;
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  min-height: 20px;
}

.empty {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--n-gap-xl);
  border: 1px dashed var(--n-border);
  border-radius: var(--n-radius-lg);
  color: var(--n-text-tertiary);
  font-size: var(--n-text-sm);
}
</style>
