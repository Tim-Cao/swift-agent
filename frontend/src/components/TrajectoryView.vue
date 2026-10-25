<template>
  <div class="trajectory-view">
    <div v-if="loading" class="loading">
      <i class="bi bi-arrow-repeat is-loading"></i>
      <span>加载轨迹…</span>
    </div>

    <el-empty
      v-else-if="!trajectory || trajectory.summary?.empty"
      description="该会话暂无轨迹数据(可能是早期会话,或 JSONL 尚未落盘)"
      :image-size="100"
    >
      <div class="empty-actions">
        <IconButton
          v-if="sessionId"
          icon="bi-download"
          title="下载原始 JSONL"
          @click="onExport"
        />
      </div>
    </el-empty>

    <!--
      双栏布局(对齐 deepseek TrajectoryTable):
      - 左 .timeline-pane:常驻,可滚动,放头部 + timeline
      - 右 .details-pane-container:有选中 cell 时挂载 <TrajectoryDetailsPanel>
    -->
    <div v-else class="trajectory-pane" :class="{ 'has-details': !!selectedCell }">
      <!--
        浮动工具条:会话元信息区域已移除,只把「下载 JSONL」留成右上角的
        浮动图标条。
        它浮在 timeline **上方**(绝对定位),所以左栏要留出它的高度,
        免得盖住第一行。
      -->
      <div class="floating-toolbar">
        <IconButton
          small
          icon="bi-download"
          variant="primary"
          title="下载 JSONL"
          @click="onExport"
        />
      </div>

      <div class="timeline-pane">
        <!--
          Timeline:扁平事件流(参考 deepseek-harness TrajectoryTable)。
          数据模型仍是 turn → steps,渲染层把所有"事件"(system / user /
          assistant / tool / file)拍扁成一个按时间排序的序列:
            - system(初始那条永远在 timeline 最顶部 — 对齐 deepseek
              layoutEntryOrder 的 Number.NEGATIVE_INFINITY trick)
            - 每个 turn 第一行(user / system)左上角贴 'Turn N' 角标
              + 顶部一条 2px 浅灰细线(对齐 deepseek turnLabel + 顶部分隔线)
          所有 row 视觉一致(32px 单行卡片 + kind-tag),
          点击 → 设置 selectedCell,右侧 panel 显示详情。
        -->
        <div class="timeline">
          <template v-for="(item, idx) in timelineItems" :key="idx">
            <!--
              0. Turn 分割线(独立元素,不是任何 row 的装饰)
                 结构:label 在最左 + 一条短 line 跟在 label 右边
                 跟 deepseek 不同:deepseek 是 line 全宽 + 角标盖在 line 左端,
                 我们这里把 Turn N 文本放在最前面,后面跟一条很窄(40px)
                 的水平线作为视觉提示,不占满整行。
            -->
            <div v-if="item.firstOfTurn" class="turn-divider" :data-turn="item.turn">
              <span class="turn-divider-label">
                Turn {{ item.turn + 1 }}
                <el-tag
                  v-if="item.endedReason && item.endedReason !== 'normal'"
                  size="small"
                  :type="turnTagType(item.endedReason)"
                  effect="plain"
                  class="turn-divider-tag"
                >
                  {{ turnReasonLabel(item.endedReason) }}
                </el-tag>
                <span v-if="item.duration" class="turn-divider-time">{{ item.duration }}</span>
              </span>
              <span class="turn-divider-line" aria-hidden="true"></span>
            </div>

            <!-- ① System prompt 单行卡片 -->
            <div
              v-if="item.kind === 'system'"
              class="step-row kind-system"
              :class="{
                'is-turn-active': isTurnActive(item),
                'is-selected': isSelected(item),
              }"
              @click="selectCell(item)"
            >
              <span class="kind-tag tag-system">
                <i class="bi bi-tools kind-icon"></i>
                System
              </span>
              <el-tooltip
                :content="promptChangeLabel(item.sp.reason)"
                placement="top"
                effect="dark"
              >
                <span class="step-summary">
                  {{ promptChangeLabel(item.sp.reason) }}
                </span>
              </el-tooltip>
              <span class="step-summary-inline">
                {{ item.sp.content.length }} 字符
              </span>
            </div>

            <!-- ② User message 单行卡片 -->
            <div
              v-else-if="item.kind === 'user-message'"
              class="step-row kind-user"
              :class="{
                'is-turn-active': isTurnActive(item),
                'is-selected': isSelected(item),
              }"
              @click="selectCell(item)"
            >
              <span class="kind-tag tag-user">User</span>
              <el-tooltip :content="item.content" placement="top" effect="dark">
                <span class="step-summary">{{ item.content }}</span>
              </el-tooltip>
            </div>

            <!-- ③ 其它 step(tool / assistant / file)— 走 TrajectoryStepItem -->
            <div
              v-else-if="item.kind === 'step'"
              class="step-row"
              :class="{
                'is-turn-active': isTurnActive(item),
                'is-selected': isSelected(item),
              }"
              @click="selectCell(item)"
            >
              <TrajectoryStepItem :step="item.step" />
            </div>
          </template>

          <div v-if="!timelineItems.length" class="empty-timeline">
            (暂无事件)
          </div>
        </div>
      </div>

      <!-- 右栏:详情抽屉(默认不展示,只有点 cell 才滑出) -->
      <Transition name="drawer-slide">
        <div v-if="selectedCell" class="details-pane-container">
          <TrajectoryDetailsPanel
            :cell="selectedCell"
            :tools="tools"
            :fallback-tool-ids="fallbackToolIds"
            @close="clearSelection"
          />
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getTrajectory, exportSessionLog } from '../api/trajectory'
import { listTools } from '../api/tools'
import { getAgent } from '../api/agents'
import { getSession } from '../api/sessions'
import IconButton from './IconButton.vue'
import TrajectoryStepItem from './TrajectoryStepItem.vue'
import TrajectoryDetailsPanel from './TrajectoryDetailsPanel.vue'
import { useChat } from '../stores/chat'

const props = defineProps({
  sessionId: { type: String, default: null },
  /** ChatWindow 传下来:trajectory tab 当前是否可见。轮询只在可见 + 流式时开 */
  active: { type: Boolean, default: false },
})

const loading = ref(false)
const trajectory = ref(null)
// 单选模式(对齐 deepseek selectedRecordId):保存当前选中的 cell item
const selectedCell = ref(null)
// tools 表全量(「工具」标签页把 tool_ids 换成工具名 / 描述)
const tools = ref([])
// 老会话的 system_prompt 事件没记 tool_ids → 按会话绑定的 agent 回退解析
const fallbackToolIds = ref([])

/**
 * 把 system_prompts 跟 turns 合并成一个扁平事件序列(对齐 deepseek
 * layoutEntryOrder + enclosingPromptTurn):
 * - initial 永远排第一(NEGATIVE_INFINITY trick)
 * - change 按 time 落到对应 turn 第一行之前
 * - firstOfTurn(对齐 deepseek flattenRecords):**永远只给该 turn 第一个
 *   非 system cell** —— system cell(无论 initial 还是 change)从
 *   来不打 turnStart 标。user_message 有 → user 是 firstOfTurn;
 *   没有 user_message → 第一个 step 兜底。
 *   这样 Turn N 角标 + 顶部 2px 细线总是落在 user 行,而不是 system 行
 *   (对齐 deepseek `tr[data-turn-start='true']:not(:first-child) td::before`)。
 */
const timelineItems = computed(() => {
  const items = []
  const sps = trajectory.value?.system_prompts || []
  const turns = trajectory.value?.turns || []
  let spIdx = 0

  for (let i = 0; i < turns.length; i++) {
    const turn = turns[i]
    const turnEndedReason = turn.ended_reason && turn.ended_reason !== 'normal'
      ? turn.ended_reason
      : null
    const duration = formatDuration(turn.started_at, turn.ended_at) || null
    const turnMeta = { turn: turn.turn, endedReason: turnEndedReason, duration }
    let turnStartAssigned = false  // per-turn: 第一个非 system cell 拿到 firstOfTurn

    // 1. 该 turn 之前的 system_prompts — 永远不打 firstOfTurn
    //    (initial 自然出现在 turn 0 之前;change 按 time 落到 enclosing turn 之前)
    while (spIdx < sps.length && sps[spIdx].time <= turn.started_at) {
      items.push({
        kind: 'system',
        sp: sps[spIdx],
        firstOfTurn: false,
        ...turnMeta,
      })
      spIdx++
    }

    // 2. user-message(如果有)— turn 第一个非 system cell,打 firstOfTurn
    if (turn.user_message) {
      items.push({
        kind: 'user-message',
        content: turn.user_message,
        source: turn.user_message_source || null,
        firstOfTurn: !turnStartAssigned,
        ...turnMeta,
      })
      turnStartAssigned = true
    }

    // 3. turn 的 steps — 兜底(turn 无 user_message 时,第一个 step 拿 firstOfTurn)
    for (let j = 0; j < turn.steps.length; j++) {
      items.push({
        kind: 'step',
        step: turn.steps[j],
        firstOfTurn: !turnStartAssigned,
        ...turnMeta,
      })
      turnStartAssigned = true
    }
  }
  // 兜底:剩余 system_prompts(理论上都该在最后 turn 之前,但容错)
  while (spIdx < sps.length) {
    items.push({ kind: 'system', sp: sps[spIdx], firstOfTurn: false })
    spIdx++
  }
  return items
})

watch(
  () => props.sessionId,
  async (sid) => {
    if (sid) {
      await load()
    } else {
      trajectory.value = null
      selectedCell.value = null
    }
  },
  { immediate: true },
)

// 拿到 chat store 的 isStreaming(用来动态调轮询间隔)
const { isStreaming } = useChat()

/**
 * trajectory tab 可见就持续轮询,实时拉取新增事件。
 *
 * 设计要点:
 * - 只要 props.active === true 且 sessionId 存在,就轮询(不管
 *   isStreaming)。原因:典型 UX 是"用户在 chat tab 发消息 → 切到
 *   trajectory tab 看结果",这时 isStreaming 已经 false,如果按
 *   streaming gating,新消息永远不会自动出现。
 * - 流式时 1.5s(响应要快),否则 5s(节省服务器资源,容忍 stale)。
 * - 切走 tab(active=false)或换会话(sid 变)→ 立即停掉。
 * - silent 轮询失败不打扰用户,等下一次再试。
 * - in-flight 守卫:慢请求不叠加。
 */
let pollTimer = null
let pollInFlight = false
const POLL_INTERVAL_STREAMING_MS = 1500
const POLL_INTERVAL_IDLE_MS = 5000

function clearPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPoll(sid, streaming) {
  const interval = streaming ? POLL_INTERVAL_STREAMING_MS : POLL_INTERVAL_IDLE_MS
  pollTimer = setInterval(async () => {
    if (pollInFlight) return
    pollInFlight = true
    try {
      trajectory.value = await getTrajectory(sid)
    } catch (_e) {
      // silent: 后台轮询失败不打扰用户,等下一次再试
    } finally {
      pollInFlight = false
    }
  }, interval)
}

watch(
  [() => props.sessionId, () => props.active, isStreaming],
  ([sid, active, streaming], [_sidOld, activeOld, streamingOld]) => {
    clearPoll()
    if (!sid || !active) return
    // active tab + 有 sessionId → 立即起一次轮询
    startPoll(sid, streaming)
  },
  { immediate: true },
)

onUnmounted(() => {
  clearPoll()
})

async function load() {
  if (!props.sessionId) return
  loading.value = true
  try {
    trajectory.value = await getTrajectory(props.sessionId)
    // 切换会话时清空选中
    selectedCell.value = null
    // 工具列表 + 老会话的 tool_ids 回退(互不依赖,失败不挡轨迹展示)
    loadTools()
    loadFallbackToolIds()
  } catch (e) {
    ElMessage.error(`加载轨迹失败:${e?.response?.data?.detail || e?.message || e}`)
    trajectory.value = null
  } finally {
    loading.value = false
  }
}

/** 拉 tools 表全量 —— 「工具」标签页用来把 tool_ids 换成工具名 / 描述 */
async function loadTools() {
  try {
    tools.value = await listTools()
  } catch {
    tools.value = []
  }
}

/**
 * 老会话回退:system_prompt 事件没记 tool_ids 时,按会话绑定的 agent
 * 的配置解析出它绑定了哪些工具。
 */
async function loadFallbackToolIds() {
  fallbackToolIds.value = []
  try {
    const session = await getSession(props.sessionId)
    const agentId = session?.agent_id
    if (!agentId) return
    const agent = await getAgent(agentId)
    const cfg = agent?.published
      ? agent.published_config
      : agent?.draft_config
    fallbackToolIds.value = cfg?.tool_ids || []
  } catch {
    fallbackToolIds.value = []
  }
}

function onExport() {
  if (!props.sessionId) return
  exportSessionLog(props.sessionId)
}

// ----- 选中态管理(对齐 deepseek selectedRecordId 单选) -----

/** 给一个 cell item 生成稳定 ID(用于判断"再点同一 cell") */
function getCellId(item) {
  if (item.kind === 'system') return `system-${item.sp.seq}`
  if (item.kind === 'user-message') {
    // 每个 turn 只有一条 user-message,turn 编号足够区分
    return `user-${item.turn}`
  }
  if (item.kind === 'step') {
    // step 用 (turn, step index, kind) 区分;同一 turn 内同 step index + kind 应是同一个
    return `step-${item.step.turn}-${item.step.step}-${item.step.kind}`
  }
  return Math.random().toString(36).slice(2)
}

function isSelected(item) {
  if (!selectedCell.value) return false
  return getCellId(selectedCell.value) === getCellId(item)
}

/** 点击 cell → 选中或取消(切换语义) */
function selectCell(item) {
  if (isSelected(item)) {
    selectedCell.value = null
  } else {
    selectedCell.value = item
  }
}

function clearSelection() {
  selectedCell.value = null
}

/**
 * 对齐 deepseek `activeTurn` + turnRail:
 * - 如果选中的 cell 属于某个 turn,该 turn 整列都画 2px 浅蓝 rail
 *   ("当前正在看的是 Turn N"),不是只画选中那一行
 * - initial system prompt 不属于任何 turn(钉在 timeline 顶部),不触发 turn rail
 */
const activeTurn = computed(() => {
  if (!selectedCell.value) return null
  const sel = selectedCell.value
  // initial system 钉在顶部,不属于具体 turn
  if (sel.kind === 'system' && sel.sp?.reason === 'initial') return null
  if (sel.turn != null) return sel.turn
  if (sel.step?.turn != null) return sel.step.turn
  return null
})

function isTurnActive(item) {
  if (activeTurn.value == null) return false
  if (item == null) return false
  if (item.turn != null) return item.turn === activeTurn.value
  if (item.step?.turn != null) return item.step.turn === activeTurn.value
  return false
}

// ----- helpers -----

/**
 * 对齐 deepseek-harness `promptChangeLabel` (layout.ts:771-776):
 *   initial → "Initial System Prompt"
 *   change  → "System Prompt Updated"
 * 单行概要不是 raw prompt,而是这种语义化标签。
 */
function promptChangeLabel(reason) {
  if (reason === 'initial') return 'Initial System Prompt'
  if (reason === 'change') return 'System Prompt Updated'
  return 'System Prompt'
}

function formatDuration(start, end) {
  if (!start || !end) return ''
  const ms = Math.round((end - start) * 1000)
  if (ms < 1000) return `${ms} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  const m = Math.floor(ms / 60_000)
  const s = Math.round((ms % 60_000) / 1000)
  return `${m}m ${s}s`
}

function turnReasonLabel(reason) {
  if (!reason || reason === 'normal') return '完成'
  if (reason === 'error') return '错误'
  if (reason === 'aborted') return '中止'
  return reason
}

function turnTagType(reason) {
  if (!reason || reason === 'normal') return 'success'
  if (reason === 'error') return 'danger'
  if (reason === 'aborted') return 'warning'
  return 'info'
}
</script>

<style scoped>
.trajectory-view {
  padding: 0;
  /* 撑满外层(.chat-window 的 trajectory-pane)—— 双栏布局要的是
     「左栏可滚 + 右栏抽屉贴满高度」,高度塌成内容高度会让抽屉只剩一小条 */
  height: 100%;
  min-height: 0;
}

/* ============== Loading / Empty ============== */
.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--n-gap-sm);
  padding: var(--n-gap-xl) 0;
  color: var(--n-text-tertiary);
  font-size: var(--n-text-sm);
}

/* ============== 双栏布局 ============== */
.trajectory-pane {
  display: flex;
  gap: var(--n-gap);
  align-items: stretch;
  height: 100%;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.timeline-pane {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  /* 顶部留出浮动工具条的位置(工具条绝对定位在它上面) */
  padding: 38px 4px 0;
  transition: margin-right 0.25s ease;
}

.details-pane-container {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: clamp(320px, 38%, 440px);
  max-width: calc(100vw - 280px);
  display: flex;
  flex-direction: column;
  min-height: 0;
  z-index: 10;
  box-shadow: -6px 0 20px rgba(15, 15, 15, 0.08);
  border-left: 1px solid var(--n-border);
  background: var(--n-bg);
}

/* ----- 抽屉滑入/滑出动画 ----- */
.drawer-slide-enter-active,
.drawer-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.2s ease;
  will-change: transform;
}
.drawer-slide-enter-from,
.drawer-slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* ============== 浮动工具条 ============== */
/* 会话元信息区域已移除;刷新 / 下载 JSONL 收成右上角的浮动图标条 */
.floating-toolbar {
  position: absolute;
  top: 0;
  right: 4px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: var(--n-gap-xs);
  padding: 4px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--n-bg) 88%, transparent);
  backdrop-filter: blur(6px);
}
/* 详情抽屉展开时,工具条往左让位,不被抽屉盖住 */
.trajectory-pane.has-details .floating-toolbar {
  right: calc(clamp(320px, 38%, 440px) + 8px);
}

/* ============== Timeline(扁平事件流) ============== */
.timeline {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

/* ----- 通用 step-row(扁平化事件流的每一行) ----- */
.step-row {
  display: flex;
  align-items: center;
  gap: var(--n-gap-sm);
  background: var(--n-bg-card);
  border: 1px solid var(--n-border);
  border-radius: var(--n-radius);
  padding: 0 10px;
  min-height: 30px;
  font-size: var(--n-text-sm);
  overflow: hidden;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
}
.step-row:hover {
  background: var(--n-bg-code);
}

/* 选中态 */
.step-row.is-selected {
  background: var(--n-accent-bg);
  box-shadow: inset 3px 0 0 var(--n-accent);
}
.step-row.is-selected:hover {
  background: var(--n-accent-bg);
}

/* Active-turn rail */
.step-row.is-turn-active {
  box-shadow: inset 2px 0 0 var(--n-accent-border);
}
.step-row.is-turn-active.is-selected {
  box-shadow: inset 3px 0 0 var(--n-accent);
}

/* ----- Turn 分割线 ----- */
.turn-divider {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: var(--n-gap-md) 4px var(--n-gap-sm);
  user-select: none;
}
.turn-divider-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--n-text-xs);
  font-weight: 600;
  color: var(--n-text-secondary);
  font-family: var(--n-font-mono);
  letter-spacing: 0.4px;
  flex-shrink: 0;
  white-space: nowrap;
}
.turn-divider-line {
  width: 40px;
  height: 1px;
  background: var(--n-border-strong);
  flex-shrink: 0;
}
.turn-divider :deep(.turn-divider-tag) {
  font-size: 10px !important;
  height: 16px !important;
  line-height: 16px !important;
  padding: 0 4px !important;
}
.turn-divider-time {
  font-size: 10px;
  font-family: var(--n-font-mono);
  color: var(--n-text-tertiary);
  font-weight: 400;
}

/* ----- kind-tag ----- */
.kind-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 18px;
  line-height: 18px;
  padding: 0 6px;
  font-size: 10px;
  font-weight: 600;
  border-radius: var(--n-radius-sm);
  white-space: nowrap;
  font-family: var(--n-font-mono);
  letter-spacing: 0.35px;
  flex-shrink: 0;
}
.kind-icon {
  font-size: 11px;
  line-height: 1;
}
.tag-user {
  color: var(--n-accent);
  background: var(--n-accent-bg);
}
.tag-system {
  color: var(--n-text-secondary);
  background: var(--n-bg-active);
}

/* 单行 preview(每 row 右侧的概要文字) */
.step-summary {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--n-text-secondary);
  font-size: var(--n-text-sm);
}
.step-summary-inline {
  color: var(--n-text-tertiary);
  font-size: var(--n-text-xs);
  font-family: var(--n-font-mono);
  flex-shrink: 0;
  margin-left: auto;
}

/* ----- 空 timeline 占位 ----- */
.empty-timeline {
  color: var(--n-text-tertiary);
  font-size: var(--n-text-xs);
  text-align: center;
  padding: var(--n-gap-lg) 0;
}

/* ----- 空状态 el-empty 里的两个按钮 ----- */
.empty-actions {
  display: flex;
  gap: var(--n-gap-sm);
  justify-content: center;
  margin-top: 4px;
}
</style>
