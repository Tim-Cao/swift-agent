<template>
  <!--
    参考 deepseek-harness TrajectoryTable:
    - 永远单行概要(32px min-height + ellipsis)
    - 选中态由外层 TrajectoryView 控制(.is-selected 加在 step-row 上)
    - 详情通过 TrajectoryDetailsPanel 在右侧 panel 展示,本组件不再就地展开
  -->
  <div
    :class="['step-item', `kind-${step.kind}`]"
  >
    <!-- ============ 单行概要(始终可见) ============ -->
    <div class="step-line">
      <!-- Tool step:CSS grid 两栏 — 左 name+args,右 → result -->
      <template v-if="step.kind === 'tool' && step.tool">
        <span class="kind-tag tag-tool">Tool</span>
        <span class="step-summary-grid">
          <span class="tool-call">
            <span class="tool-name">{{ step.tool.name }}</span>
            <span v-if="toolArgsText" class="tool-args">{{ toolArgsText }}</span>
          </span>
          <span v-if="toolResultText" :class="['tool-result', { 'is-error': step.tool.is_error }]">
            <span class="tool-arrow">{{ step.tool.is_error ? '→ ✗' : '→' }}</span>
            <span class="tool-result-text">{{ toolResultText }}</span>
          </span>
        </span>
        <span class="step-latency">{{ formatLatency(step.latency_ms) }}</span>
      </template>

      <!-- Assistant step:单行 preview(flatten markdown) -->
      <template v-else-if="step.kind === 'assistant_message' && step.assistant">
        <span class="kind-tag tag-assistant">Assistant</span>
        <span class="step-summary" :title="assistantPreview">
          {{ assistantPreview || '(空)' }}
        </span>
        <span class="step-latency">{{ formatLatency(step.latency_ms) }}</span>
        <span v-if="step.assistant.input_tokens != null" class="tok">
          in {{ step.assistant.input_tokens }}
        </span>
        <span v-if="step.assistant.output_tokens != null" class="tok">
          out {{ step.assistant.output_tokens }}
        </span>
      </template>

      <!-- File step -->
      <template v-else-if="step.kind === 'file' && step.file_meta">
        <span class="kind-tag tag-file">File</span>
        <span class="step-name">{{ step.file_meta.filename }}</span>
        <span class="step-summary-inline">{{ formatBytes(step.file_meta.size_bytes) }}</span>
      </template>

      <template v-else>
        <span class="kind-tag tag-system">Unknown</span>
        <span class="step-name">{{ step.kind }}</span>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MarkdownView from './MarkdownView.vue'  // 保留 import,虽然不再就地展开(MarkdownView 在 panel 里用)

const props = defineProps({
  step: { type: Object, required: true },
})

// ----- 单行 preview(参考 deepseek trajectoryPreviewText) -----

const PREVIEW_LIMIT = 200  // 单行 preview 截断字符数

/**
 * Markdown → 单行纯文本 preview。
 *
 * 不走完整 GFM AST(那是 deepseek 的方案,较重),而是常见 markdown 标记
 * 的正则 strip + 空白折叠 + 截断。对 LLM 输出的标准 markdown(标题/列表/
 * 粗体/代码块/链接)足够 strip 干净,单行概要不会带 `**` / `[text](url)`
 * 等符号。
 */
function flattenMarkdown(s) {
  if (!s) return ''
  let t = String(s)
  // fenced code blocks
  t = t.replace(/```[\s\S]*?```/g, (m) => m.replace(/```\w*\n?/g, '').replace(/```$/g, ''))
  // inline code
  t = t.replace(/`([^`]+)`/g, '$1')
  // images ![alt](url) → alt
  t = t.replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
  // links [text](url) → text
  t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
  // bold **text** / __text__ → text
  t = t.replace(/(\*\*|__)(.+?)\1/g, '$2')
  // italic *text* / _text_ → text
  t = t.replace(/(\*|_)(.+?)\1/g, '$2')
  // headers # → 删前缀
  t = t.replace(/^#+\s+/gm, '')
  // list bullets -, *, +
  t = t.replace(/^[-*+]\s+/gm, '')
  // ordered list 1. → 删前缀
  t = t.replace(/^\d+\.\s+/gm, '')
  // blockquote > → 删前缀
  t = t.replace(/^>\s*/gm, '')
  // 折叠所有空白到单空格(保留段间分隔,这里无段间分隔概念,所以全 fold)
  t = t.replace(/\s+/g, ' ').trim()
  if (t.length > PREVIEW_LIMIT) {
    t = t.slice(0, PREVIEW_LIMIT) + '…'
  }
  return t
}

// ----- Tool 单行 preview -----

/** 工具 step 左侧:`name + args`(`k=v, k=v` 形式) */
const toolArgsText = computed(() => {
  const t = props.step.tool
  if (!t) return ''
  return formatArgsOneline(t.input || {})
})

/** 工具 step 右侧:`→ result preview` */
const toolResultText = computed(() => {
  const t = props.step.tool
  if (!t) return ''
  return flattenMarkdown(t.output || '')
})

function formatArgsOneline(input) {
  if (!input || Object.keys(input).length === 0) return ''
  const parts = []
  for (const [k, v] of Object.entries(input)) {
    const vstr = typeof v === 'string' ? v : JSON.stringify(v)
    const flat = flattenMarkdown(vstr).slice(0, 60)
    parts.push(`${k}=${flat}`)
  }
  const s = parts.join(', ')
  return s.length > 160 ? s.slice(0, 160) + '…' : s
}

// ----- Assistant 单行 preview -----

const assistantPreview = computed(() => {
  const a = props.step.assistant
  if (!a) return ''
  return flattenMarkdown(a.content || '')
})

// ----- helpers(供 panel 也可能用,但保留在这里作为 fallback) -----

function formatLatency(ms) {
  if (ms == null) return ''
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

function formatBytes(n) {
  if (n == null) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}
</script>

<style scoped>
/* ----- 卡片外壳 ----- */
.step-item {
  background: transparent;  /* 由外层 .step-row 提供背景,避免双层背景 */
  font-size: 13px;
  transition: background 0.15s;
}

/* 左侧色条:整段扫读(由外层 .step-row 控制 3px 边框) */
.step-item.kind-tool {
  /* noop — left rail 来自外层 .step-row.kind-tool */
}
.step-item.kind-assistant_message {
  /* noop */
}
.step-item.kind-file {
  /* noop */
}

/* ----- 单行概要行 ----- */
.step-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  min-height: 32px;
  padding: 0;
  overflow: hidden;
}

/* Tool step:CSS grid 两栏(name+args / → result) */
.step-summary-grid {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) minmax(0, 1fr);
  gap: 8px;
  flex: 1;
  min-width: 0;
  align-items: center;
}
.tool-call {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}
.tool-name {
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #303133;
  flex-shrink: 0;
}
.tool-args {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #606266;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.tool-result {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  color: #909399;
  font-size: 12px;
}
.tool-result.is-error {
  color: #f56c6c;
}
.tool-arrow {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  flex-shrink: 0;
}
.tool-result-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* Assistant / File 单行 preview */
.step-summary {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #606266;
  font-size: 13px;
}
.step-summary-inline {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  flex-shrink: 0;
}

/* kind tag —— 跟 TrajectoryView 保持一致
 * 对齐 deepseek TrajectoryTable.module.css:461-475 / 592-705
 */
.kind-tag {
  display: inline-block;
  height: 19px;
  line-height: 19px;
  padding: 0 6px;
  font-size: 10px;
  font-weight: 650;
  border-radius: 4px;
  white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: 0.35px;
  flex-shrink: 0;
}
.tag-system {
  color: #909399;
  background: #f4f4f5;
}
/* assistant → violet (对齐 deepseek .assistantVioletBright) */
.tag-assistant {
  color: #7c3aed;
  background: #f3e8ff;
}
.tag-tool {
  color: #e6a23c;
  background: #fdf6ec;
}
.tag-file {
  color: #9c27b0;
  background: #f3e5f5;
}

.step-name {
  font-weight: 600;
  color: #303133;
  flex-shrink: 0;
  white-space: nowrap;
}
.step-latency {
  color: #909399;
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  flex-shrink: 0;
}
.tok {
  color: #909399;
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  flex-shrink: 0;
}
</style>