<template>
  <!--
    右侧详情 panel(对齐 deepseek TrajectoryTable <aside class="details">)
    - 桌面端常驻 inline panel
    - 根据 cell.kind 渲染不同内容
    - header 有 × 关闭按钮(等价再点同一 cell)
    - system / user 两类 cell 有标签页(见 tabList)
  -->
  <aside class="details-pane">
    <header class="details-pane-header">
      <div class="details-pane-title">
        <i v-if="cellKindIcon" class="bi details-pane-icon" :class="cellKindIcon"></i>
        <span class="details-pane-kind">{{ kindLabel }}</span>
        <span v-if="kindSubLabel" class="details-pane-sub">{{ kindSubLabel }}</span>
      </div>
      <button class="details-pane-close" aria-label="关闭" @click="emit('close')">
        <i class="bi bi-x-lg"></i>
      </button>
    </header>

    <!-- 标签页(Notion 风格细条) -->
    <nav v-if="tabList.length" class="detail-tabs" role="tablist">
      <button
        v-for="t in tabList"
        :key="t.id"
        type="button"
        role="tab"
        :aria-selected="activeTab === t.id"
        :class="['detail-tab', { 'detail-tab-active': activeTab === t.id }]"
        @click="activeTab = t.id"
      >
        {{ t.label }}
        <span v-if="t.count != null" class="detail-tab-count">{{ t.count }}</span>
      </button>
    </nav>

    <div class="details-pane-body">
      <!-- ============ System prompt · 系统提示词 ============ -->
      <template v-if="isSystem && activeTab === 'prompt'">
        <pre class="prompt-plain">{{ cell.sp.content }}</pre>
      </template>

      <!-- ============ System prompt · 工具 ============ -->
      <template v-else-if="isSystem && activeTab === 'tools'">
        <div v-if="resolvedTools.length" class="tool-list">
          <div v-for="t in resolvedTools" :key="t.id" class="tool-item">
            <div class="tool-head">
              <i class="bi bi-tools tool-icon"></i>
              <span class="tool-name">{{ t.display_name || t.name }}</span>
              <el-tag v-if="t.builtin" size="small" type="info" effect="plain">内置</el-tag>
            </div>
            <div class="tool-meta">
              <code class="meta-val">{{ t.name }}</code>
            </div>
            <div v-if="t.description" class="tool-desc">{{ t.description }}</div>
          </div>
        </div>
        <div v-else class="empty-body">
          {{ toolEmptyHint }}
        </div>
      </template>

      <!-- ============ User message · 概述 ============ -->
      <template v-else-if="isUser && activeTab === 'overview'">
        <div class="detail-block">
          <div class="detail-label">概述</div>
          <div class="meta-row">
            <span class="meta-key">轮次</span>
            <span class="meta-val">Turn {{ (cell.turn ?? 0) + 1 }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-key">字符数</span>
            <span class="meta-val">{{ userContent.length }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-key">行数</span>
            <span class="meta-val">{{ userLineCount }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-key">来源</span>
            <span class="meta-val">{{ source ? '已记录' : '未记录' }}</span>
          </div>
        </div>
      </template>

      <!-- ============ User message · 预览 ============ -->
      <template v-else-if="isUser && activeTab === 'preview'">
        <MarkdownView v-if="userContent" :content="userContent" />
        <div v-else class="empty-body">(空内容)</div>
      </template>

      <!-- ============ User message · 原始内容 ============ -->
      <template v-else-if="isUser && activeTab === 'raw'">
        <pre class="prompt-pre">{{ userContent }}</pre>
      </template>

      <!-- ============ User message · 来源 ============ -->
      <template v-else-if="isUser && activeTab === 'source'">
        <template v-if="source">
          <div class="detail-block">
            <div class="detail-label">客户端调用信息</div>
            <div class="meta-row">
              <span class="meta-key">kind</span>
              <code class="meta-val">{{ source.kind ?? '—' }}</code>
            </div>
            <div class="meta-row">
              <span class="meta-key">rpcId</span>
              <code class="meta-val">{{ source.rpcId ?? '—' }}</code>
            </div>
            <div class="meta-row">
              <span class="meta-key">clientTimeZone</span>
              <code class="meta-val">{{ source.clientTimeZone ?? '—' }}</code>
            </div>
          </div>
          <div class="detail-block">
            <div class="detail-label">原始 JSON</div>
            <pre class="prompt-pre">{{ formatJson(source) }}</pre>
          </div>
        </template>
        <div v-else class="empty-body">
          该消息没有记录来源信息(旧会话或客户端未上报)
        </div>
      </template>

      <!-- ============ Tool call ============ -->
      <template v-else-if="cell.kind === 'step' && cell.step?.kind === 'tool' && cell.step.tool">
        <div class="detail-block">
          <div class="detail-label">
            工具调用 · {{ cell.step.tool.name }}
            <span v-if="cell.step.tool.is_error" class="err-badge">ERROR</span>
          </div>
          <div v-if="cell.step.tool.call_id" class="meta-row">
            <span class="meta-key">call_id</span>
            <code class="meta-val">{{ cell.step.tool.call_id }}</code>
          </div>
          <div v-if="cell.step.tool.latency_ms != null" class="meta-row">
            <span class="meta-key">latency</span>
            <span class="meta-val">{{ formatLatency(cell.step.tool.latency_ms) }}</span>
          </div>
        </div>
        <div v-if="hasInput(cell.step.tool.input)" class="detail-block">
          <div class="detail-label">输入</div>
          <pre class="prompt-pre">{{ formatJson(cell.step.tool.input) }}</pre>
        </div>
        <div v-if="cell.step.tool.output" class="detail-block">
          <div class="detail-label">输出</div>
          <pre class="prompt-pre">{{ cell.step.tool.output }}</pre>
        </div>
      </template>

      <!-- ============ Assistant message ============ -->
      <template v-else-if="cell.kind === 'step' && cell.step?.kind === 'assistant_message' && cell.step.assistant">
        <div class="detail-block">
          <div class="detail-label">
            Assistant 消息
            <span v-if="cell.step.latency_ms != null" class="meta-inline">{{ formatLatency(cell.step.latency_ms) }}</span>
          </div>
          <MarkdownView v-if="cell.step.assistant.content" :content="cell.step.assistant.content" />
          <div v-else class="empty-body">(空内容)</div>
        </div>
        <div
          v-if="cell.step.assistant.input_tokens != null || cell.step.assistant.output_tokens != null"
          class="detail-block"
        >
          <div class="detail-label">Token 用量</div>
          <div class="token-stats">
            <span v-if="cell.step.assistant.input_tokens != null">
              <span class="meta-key">input</span>
              <code class="meta-val">{{ cell.step.assistant.input_tokens }}</code>
            </span>
            <span v-if="cell.step.assistant.output_tokens != null">
              <span class="meta-key">output</span>
              <code class="meta-val">{{ cell.step.assistant.output_tokens }}</code>
            </span>
          </div>
        </div>
      </template>

      <!-- ============ File ============ -->
      <template v-else-if="cell.kind === 'step' && cell.step?.kind === 'file' && cell.step.file_meta">
        <div class="detail-block">
          <div class="detail-label">文件元信息</div>
          <pre class="prompt-pre">{{ formatJson(cell.step.file_meta) }}</pre>
        </div>
        <div v-if="cell.step.file_meta.url" class="detail-block">
          <el-link :href="cell.step.file_meta.url" type="primary" target="_blank">
            <i class="bi bi-box-arrow-up-right"></i>
            打开文件
          </el-link>
        </div>
      </template>

      <!-- ============ 兜底 ============ -->
      <template v-else>
        <div class="empty-body">(未识别的 cell 类型)</div>
        <pre class="prompt-pre">{{ formatJson(cell) }}</pre>
      </template>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import MarkdownView from './MarkdownView.vue'

const props = defineProps({
  cell: { type: Object, required: true },
  /**
   * 全部工具列表(tools 表的记录)。
   *
   * 「工具」标签页据此把 system_prompt 事件里记的 tool_ids 换成
   * 工具的展示名 / 描述。父组件(TrajectoryView)加载一次传进来。
   */
  tools: { type: Array, default: () => [] },
  /**
   * 回退用的 tool_ids(老会话的 system_prompt 事件没记 tool_ids)。
   * 父组件按「会话绑定的 agent → agent 配置」解析出来。
   */
  fallbackToolIds: { type: Array, default: () => [] },
})

const emit = defineEmits(['close'])

// ----- 头部标题 / icon / sub label -----

const kindLabel = computed(() => {
  if (props.cell.kind === 'system') return 'System'
  if (props.cell.kind === 'user-message') return 'User'
  if (props.cell.kind === 'step') {
    const s = props.cell.step
    if (s?.kind === 'tool') return `Tool · ${s.tool?.name || ''}`
    if (s?.kind === 'assistant_message') return 'Assistant'
    if (s?.kind === 'file') return 'File'
    return s?.kind || 'Step'
  }
  return 'Cell'
})

const kindSubLabel = computed(() => {
  if (props.cell.kind === 'system') {
    return props.cell.sp?.reason === 'initial' ? 'Initial' : 'Updated'
  }
  if (props.cell.kind === 'user-message') {
    return `Turn ${(props.cell.turn ?? 0) + 1}`
  }
  if (props.cell.kind === 'step') {
    const s = props.cell.step
    if (s?.kind === 'assistant_message') {
      const latency = s.latency_ms != null ? formatLatency(s.latency_ms) : ''
      return latency ? `Turn ${(s.turn ?? 0) + 1} · ${latency}` : `Turn ${(s.turn ?? 0) + 1}`
    }
    return `Turn ${(s?.turn ?? 0) + 1}`
  }
  return ''
})

const cellKindIcon = computed(() => {
  if (props.cell.kind === 'system') return 'bi-sliders'
  if (props.cell.kind === 'user-message') return 'bi-person'
  if (props.cell.kind === 'step') {
    const s = props.cell.step
    if (s?.kind === 'tool') return 'bi-tools'
    if (s?.kind === 'file') return 'bi-file-earmark'
  }
  return null
})

// ----- 标签页 -----

const isSystem = computed(() => props.cell.kind === 'system' && !!props.cell.sp)
const isUser = computed(() => props.cell.kind === 'user-message')

const userContent = computed(() => props.cell?.content ?? '')
const userLineCount = computed(() => {
  const c = userContent.value
  if (!c) return 0
  return c.split('\n').length
})
const source = computed(() => props.cell?.source || null)

/**
 * 「工具」标签页的工具列表。
 *
 * 数据来源(后端记录 + 前端回退):
 * - 优先用 system_prompt 事件里记的 tool_ids(v11.4 起写入)
 * - 老会话没有 tool_ids → 用父组件按「会话绑定的 agent」解析出来的
 *   fallbackToolIds
 * tool_ids 可能是工具 id,也可能是注册名 —— 两种都能对上。
 */
const resolvedTools = computed(() => {
  if (!isSystem.value) return []
  const ids = props.cell.sp?.tool_ids?.length
    ? props.cell.sp.tool_ids
    : props.fallbackToolIds
  if (!ids?.length) return []
  const byId = new Map()
  const byName = new Map()
  for (const t of props.tools) {
    byId.set(t.id, t)
    byName.set(t.name, t)
  }
  const out = []
  const seen = new Set()
  for (const raw of ids) {
    const key = String(raw)
    const t = byId.get(key) || byName.get(key)
    if (!t || seen.has(t.id)) continue
    seen.add(t.id)
    out.push(t)
  }
  return out
})

const toolEmptyHint = computed(() => {
  const ids = props.cell?.sp?.tool_ids
  if (ids?.length) return '记录的工具 id 在工具表里没有对应记录'
  return '该系统提示词没有绑定工具'
})

/**
 * 标签页配置。切 cell 时重置到第一个标签页。
 */
const tabList = computed(() => {
  if (isSystem.value) {
    return [
      { id: 'prompt', label: '系统提示词' },
      { id: 'tools', label: '工具', count: resolvedTools.value.length },
    ]
  }
  if (isUser.value) {
    return [
      { id: 'overview', label: '概述' },
      { id: 'preview', label: '预览' },
      { id: 'raw', label: '原始内容' },
      { id: 'source', label: '来源' },
    ]
  }
  return []
})

const activeTab = ref('prompt')
watch(
  () => props.cell,
  () => {
    activeTab.value = tabList.value[0]?.id || ''
  },
  { immediate: true },
)

// ----- helpers -----

function hasInput(input) {
  return input && Object.keys(input).length > 0
}

function formatJson(obj) {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

function formatLatency(ms) {
  if (ms == null) return ''
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}
</script>

<style scoped>
.details-pane {
  display: flex;
  flex-direction: column;
  background: var(--n-bg);
  border: 1px solid var(--n-border);
  border-radius: var(--n-radius-lg);
  overflow: hidden;
  height: 100%;
  min-height: 0;
}

/* ----- Header ----- */
.details-pane-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--n-gap-sm) var(--n-gap);
  border-bottom: 1px solid var(--n-border-light);
  background: var(--n-bg-card);
  flex-shrink: 0;
}
.details-pane-title {
  display: flex;
  align-items: center;
  gap: var(--n-gap-sm);
  min-width: 0;
  flex: 1;
}
.details-pane-icon {
  color: var(--n-text-tertiary);
  font-size: 14px;
  flex-shrink: 0;
}
.details-pane-kind {
  font-size: var(--n-text-sm);
  font-weight: 600;
  color: var(--n-text);
  font-family: var(--n-font-mono);
  flex-shrink: 0;
}
.details-pane-sub {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  font-family: var(--n-font-mono);
  flex-shrink: 0;
  padding: 2px 6px;
  background: var(--n-bg-code);
  border: 1px solid var(--n-border-light);
  border-radius: var(--n-radius-sm);
}
.details-pane-close {
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--n-text-tertiary);
  border-radius: var(--n-radius);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
  flex-shrink: 0;
}
.details-pane-close:hover {
  background: var(--n-bg-hover);
  color: var(--n-text);
}

/* ----- 标签页(Notion 风格细条) ----- */
.detail-tabs {
  display: flex;
  gap: var(--n-gap);
  padding: 0 var(--n-gap);
  background: var(--n-bg);
  border-bottom: 1px solid var(--n-border-light);
  flex-shrink: 0;
}
.detail-tab {
  position: relative;
  padding: 7px 0 8px;
  border: none;
  background: transparent;
  font-size: var(--n-text-xs);
  line-height: 16px;
  font-weight: 500;
  color: var(--n-text-tertiary);
  cursor: pointer;
  font-family: inherit;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.detail-tab:hover {
  color: var(--n-text-secondary);
}
.detail-tab::after {
  content: '';
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 2px;
  border-radius: 2px;
  background: transparent;
}
.detail-tab-active {
  color: var(--n-text);
}
.detail-tab-active::after {
  background: var(--n-accent);
}
.detail-tab-count {
  font-family: var(--n-font-mono);
  font-size: 10px;
  color: var(--n-text-tertiary);
  background: var(--n-bg-code);
  border-radius: var(--n-radius-sm);
  padding: 0 4px;
  line-height: 14px;
}

/* ----- Body ----- */
.details-pane-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--n-gap);
  min-height: 0;
}

.detail-block {
  margin-bottom: var(--n-gap-md);
}
.detail-block:last-child {
  margin-bottom: 0;
}
.detail-label {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: var(--n-gap-sm);
}
.meta-inline {
  font-family: var(--n-font-mono);
  color: var(--n-text-secondary);
  font-size: var(--n-text-xs);
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
  font-size: var(--n-text-xs);
}
.meta-key {
  color: var(--n-text-tertiary);
  min-width: 60px;
  font-size: var(--n-text-xs);
}
.meta-val {
  color: var(--n-text);
  font-family: var(--n-font-mono);
  font-size: var(--n-text-xs);
  word-break: break-all;
}

.err-badge {
  background: var(--n-red);
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: var(--n-radius-sm);
  font-family: var(--n-font-mono);
}

.token-stats {
  display: flex;
  gap: var(--n-gap-md);
  font-size: var(--n-text-xs);
}

/*
  pre 块:prompt / input / output / file meta
  注意:这里**不设** max-height / overflow-y —— 整个详情面板只保留
  .details-pane-body 一条竖向滚动条,内部不再嵌套滚动区。
*/
.prompt-pre {
  background: var(--n-bg-code);
  border: 1px solid var(--n-border-light);
  border-radius: var(--n-radius);
  padding: var(--n-gap-sm) var(--n-gap);
  margin: 0;
  font-family: var(--n-font-mono);
  font-size: var(--n-text-xs);
  line-height: 1.6;
  color: var(--n-text);
  white-space: pre-wrap;
  word-break: break-word;
}

/* 系统提示词正文:无边框、无背景块,跟正文一体 */
.prompt-plain {
  margin: 0;
  font-family: var(--n-font-mono);
  font-size: var(--n-text-xs);
  line-height: 1.65;
  color: var(--n-text);
  white-space: pre-wrap;
  word-break: break-word;
}

/* ----- 工具列表(系统提示词的「工具」标签页) ----- */
.tool-list {
  display: flex;
  flex-direction: column;
  gap: var(--n-gap-sm);
}
.tool-item {
  border: 1px solid var(--n-border-light);
  border-radius: var(--n-radius);
  padding: var(--n-gap-sm) var(--n-gap);
  background: var(--n-bg-card);
}
.tool-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
}
.tool-icon {
  color: var(--n-text-tertiary);
  font-size: 12px;
}
.tool-name {
  font-size: var(--n-text-sm);
  font-weight: 600;
  color: var(--n-text);
}
.tool-meta {
  margin-bottom: 3px;
}
.tool-desc {
  font-size: var(--n-text-xs);
  color: var(--n-text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

/* User message body */
.user-message-body {
  font-size: var(--n-text-sm);
  line-height: 1.65;
  color: var(--n-text);
  white-space: pre-wrap;
  word-break: break-word;
}

.empty-body {
  color: var(--n-text-tertiary);
  font-size: var(--n-text-xs);
  text-align: center;
  padding: var(--n-gap-md) 0;
}
</style>
