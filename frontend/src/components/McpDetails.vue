<template>
  <el-dialog
    :model-value="visible"
    :title="server?.name || 'MCP 详情'"
    width="720px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <!-- ---------- 基本信息 ---------- -->
    <section class="block">
      <h3 class="block-title">基本信息</h3>
      <dl class="info-grid">
        <div class="info-cell">
          <dt class="info-label">传输方式</dt>
          <dd class="info-value">{{ server?.transport_label || server?.transport || '-' }}</dd>
        </div>
        <div class="info-cell">
          <dt class="info-label">状态</dt>
          <dd class="info-value">
            <el-tag :type="statusType(server?.status)" size="small" effect="plain">
              {{ statusLabel(server?.status) }}
            </el-tag>
          </dd>
        </div>
        <div class="info-cell">
          <dt class="info-label">启用状态</dt>
          <dd class="info-value">
            <el-tag :type="server?.enabled ? 'success' : 'info'" size="small" effect="plain">
              {{ server?.enabled ? '已启用' : '已停用' }}
            </el-tag>
          </dd>
        </div>
        <div class="info-cell">
          <dt class="info-label">更新时间</dt>
          <dd class="info-value">{{ formatTime(server?.updated_at) }}</dd>
        </div>
        <div class="info-cell info-cell-wide">
          <dt class="info-label">连接方式</dt>
          <dd class="info-value info-mono">{{ server?.description || '还没有配置连接信息' }}</dd>
        </div>
        <div v-if="server?.status_detail" class="info-cell info-cell-wide">
          <dt class="info-label">状态详情</dt>
          <dd class="info-value info-mono info-detail">{{ server.status_detail }}</dd>
        </div>
      </dl>
    </section>

    <!-- ---------- 工具区域 ---------- -->
    <section class="block">
      <div class="block-head">
        <h3 class="block-title">
          工具
          <span class="tool-count">{{ tools.length }}</span>
        </h3>
        <el-button
          :loading="syncing"
          size="small"
          @click="syncTools"
        >
          <i class="bi bi-arrow-repeat"></i>
          同步工具
        </el-button>
      </div>

      <!-- 没同步过 -->
      <div v-if="!tools.length" class="tool-empty">
        <i class="bi bi-plug"></i>
        <p class="tool-empty-text">
          {{ synced ? '这个 MCP 没有提供任何工具' : '还没有同步过工具' }}
        </p>
        <p v-if="!synced" class="tool-empty-hint">
          点「同步工具」连接一次,把工具名和描述抓回来。
        </p>
      </div>

      <!-- 工具卡片 -->
      <div v-else class="tool-grid">
        <article v-for="t in tools" :key="t.name" class="tool-card">
          <header class="tool-head">
            <i class="bi bi-tools tool-icon"></i>
            <h4 class="tool-name">{{ t.name }}</h4>
          </header>
          <p v-if="t.description" class="tool-desc">{{ t.description }}</p>
          <p v-else class="tool-desc tool-desc-empty">(没有描述)</p>

          <div v-if="paramNames(t).length" class="tool-params">
            <span class="tool-params-label">参数</span>
            <div class="tool-params-list">
              <code v-for="p in paramNames(t)" :key="p" class="tool-param">{{ p }}</code>
            </div>
          </div>
        </article>
      </div>
    </section>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">关闭</el-button>
      <el-button type="primary" @click="$emit('edit')">编辑</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { syncMcpTools } from '../api/mcp'

const props = defineProps({
  visible: { type: Boolean, default: false },
  server: { type: Object, default: null },
})
const emit = defineEmits(['update:visible', 'edit', 'synced'])

const syncing = ref(false)
// 这次会话里同步过没有(用来区分「没工具」和「没同步过」)
const synced = ref(false)

const tools = computed(() => props.server?.tool_details || [])

watch(
  () => props.visible,
  (v) => {
    if (v) synced.value = (props.server?.tool_details || []).length > 0
  },
)

function statusLabel(s) {
  if (s === 'connected') return '已连接'
  if (s === 'failed') return '连接失败'
  return '未连接'
}

function statusType(s) {
  if (s === 'connected') return 'success'
  if (s === 'failed') return 'danger'
  return 'info'
}

function formatTime(v) {
  if (!v) return '-'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return String(v)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

/** 参数名列表(只取 key,描述太长就不显示了) */
function paramNames(t) {
  return Object.keys(t.parameters || {})
}

/** 同步工具:后端连一次 server,把工具名 + 描述 + 参数写回库 */
async function syncTools() {
  if (!props.server?.id) return
  syncing.value = true
  try {
    const res = await syncMcpTools(props.server.id)
    if (res.ok) {
      ElMessage.success(`同步完成,拿到 ${res.tools.length} 个工具`)
      synced.value = true
      emit('synced')
    } else {
      ElMessage.error(`同步失败:${res.error || '未知错误'}`)
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '同步失败')
  } finally {
    syncing.value = false
  }
}
</script>

<style scoped>
.block {
  margin-bottom: var(--n-gap-lg);
}

.block:last-child {
  margin-bottom: 0;
}

.block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--n-gap-sm);
  margin-bottom: var(--n-gap-sm);
}

.block-title {
  margin: 0 0 var(--n-gap-sm);
  font-size: var(--n-text-sm);
  font-weight: 600;
  color: var(--n-text-secondary);
  letter-spacing: 0.02em;
}

.block-head .block-title {
  margin-bottom: 0;
}

.tool-count {
  display: inline-block;
  min-width: 18px;
  padding: 0 5px;
  margin-left: 4px;
  border-radius: var(--n-radius-sm);
  background: var(--n-bg-active);
  color: var(--n-text-tertiary);
  font-size: var(--n-text-xs);
  font-weight: 500;
  text-align: center;
}

/* ---------- 基本信息 ---------- */

.info-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--n-gap) var(--n-gap-md);
  margin: 0;
  padding: var(--n-gap-md);
  border: 1px solid var(--n-border);
  border-radius: var(--n-radius-lg);
  background: var(--n-bg-subtle);
}

.info-cell-wide {
  grid-column: 1 / -1;
}

.info-label {
  margin: 0 0 2px;
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
}

.info-value {
  margin: 0;
  font-size: var(--n-text-sm);
  color: var(--n-text);
  word-break: break-all;
}

.info-mono {
  font-family: var(--n-font-mono);
  font-size: var(--n-text-xs);
}

.info-detail {
  color: var(--n-text-secondary);
}

/* ---------- 工具卡片 ---------- */

.tool-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--n-gap-sm);
  max-height: 320px;
  overflow-y: auto;
}

.tool-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--n-gap);
  border: 1px solid var(--n-border);
  border-radius: var(--n-radius);
  background: var(--n-bg-card);
  transition: border-color 0.12s ease;
}

.tool-card:hover {
  border-color: var(--n-border-strong);
}

.tool-head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.tool-icon {
  font-size: 13px;
  color: var(--n-text-tertiary);
  flex-shrink: 0;
}

.tool-name {
  margin: 0;
  font-size: var(--n-text-sm);
  font-weight: 600;
  font-family: var(--n-font-mono);
  color: var(--n-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-desc {
  margin: 0;
  font-size: var(--n-text-xs);
  line-height: 1.55;
  color: var(--n-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 4;
  line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tool-desc-empty {
  color: var(--n-text-tertiary);
  font-style: italic;
}

.tool-params {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

.tool-params-label {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  flex-shrink: 0;
}

.tool-params-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}

.tool-param {
  padding: 1px 5px;
  border-radius: var(--n-radius-sm);
  background: var(--n-bg-code);
  color: var(--n-text-secondary);
  font-family: var(--n-font-mono);
  font-size: 11px;
  white-space: nowrap;
}

/* ---------- 空状态 ---------- */

.tool-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: var(--n-gap-lg);
  border: 1px dashed var(--n-border);
  border-radius: var(--n-radius-lg);
  color: var(--n-text-tertiary);
}

.tool-empty i {
  font-size: 20px;
}

.tool-empty-text {
  margin: 0;
  font-size: var(--n-text-sm);
}

.tool-empty-hint {
  margin: 0;
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
}
</style>
