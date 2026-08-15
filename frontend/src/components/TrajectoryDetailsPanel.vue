<template>
  <!--
    右侧详情 panel(对齐 deepseek TrajectoryTable <aside class="details">)
    - 桌面端常驻 inline panel
    - 根据 cell.kind 渲染不同内容
    - header 有 × 关闭按钮(等价再点同一 cell)
  -->
  <aside class="details-pane">
    <header class="details-pane-header">
      <div class="details-pane-title">
        <el-icon v-if="cellKindIcon" class="details-pane-icon">
          <component :is="cellKindIcon" />
        </el-icon>
        <span class="details-pane-kind">{{ kindLabel }}</span>
        <span v-if="kindSubLabel" class="details-pane-sub">{{ kindSubLabel }}</span>
      </div>
      <button class="details-pane-close" aria-label="关闭" @click="emit('close')">
        <el-icon><Close /></el-icon>
      </button>
    </header>

    <div class="details-pane-body">
      <!-- ============ System prompt ============ -->
      <template v-if="cell.kind === 'system' && cell.sp">
        <div class="detail-block">
          <div class="detail-label">系统提示词({{ cell.sp.content.length }} 字符)</div>
          <pre class="prompt-pre">{{ cell.sp.content }}</pre>
        </div>
      </template>

      <!-- ============ User message ============ -->
      <template v-else-if="cell.kind === 'user-message'">
        <div class="detail-block">
          <div class="detail-label">用户消息</div>
          <div class="user-message-body">{{ cell.content }}</div>
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
            <el-icon><Link /></el-icon>
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
import { computed } from 'vue'
import { Close, Link } from '@element-plus/icons-vue'
import MarkdownView from './MarkdownView.vue'

const props = defineProps({
  cell: { type: Object, required: true },
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
  if (props.cell.kind === 'system') return 'Tools'
  if (props.cell.kind === 'user-message') return 'User'
  if (props.cell.kind === 'step') {
    const s = props.cell.step
    if (s?.kind === 'tool') return 'Tools'
    if (s?.kind === 'file') return 'Document'
  }
  return null
})

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
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  height: 100%;
  min-height: 0;
}

/* ----- Header ----- */
.details-pane-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid #ebeef5;
  background: #fafbfc;
  flex-shrink: 0;
}
.details-pane-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.details-pane-icon {
  color: #909399;
  font-size: 14px;
  flex-shrink: 0;
}
.details-pane-kind {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  flex-shrink: 0;
}
.details-pane-sub {
  font-size: 11px;
  color: #909399;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  flex-shrink: 0;
  padding: 2px 6px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 3px;
}
.details-pane-close {
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  background: transparent;
  color: #909399;
  border-radius: 4px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
  flex-shrink: 0;
}
.details-pane-close:hover {
  background: #ebeef5;
  color: #303133;
}

/* ----- Body ----- */
.details-pane-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  min-height: 0;
}

.detail-block {
  margin-bottom: 16px;
}
.detail-block:last-child {
  margin-bottom: 0;
}
.detail-label {
  font-size: 11px;
  color: #909399;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.meta-inline {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #606266;
  font-size: 11px;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  font-size: 12px;
}
.meta-key {
  color: #909399;
  min-width: 60px;
  font-size: 11px;
}
.meta-val {
  color: #303133;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  word-break: break-all;
}

.err-badge {
  background: #f56c6c;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.token-stats {
  display: flex;
  gap: 16px;
  font-size: 12px;
}

/* pre 块:prompt / input / output / file meta */
.prompt-pre {
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 10px 12px;
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 600px;
  overflow-y: auto;
}

/* User message body:大字号 */
.user-message-body {
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
}

.empty-body {
  color: #c0c4cc;
  font-size: 12px;
  text-align: center;
  padding: 16px 0;
}
</style>