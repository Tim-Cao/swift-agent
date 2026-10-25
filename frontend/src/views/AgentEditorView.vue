<template>
  <div class="editor">
    <!-- 顶部栏 -->
    <div class="editor-head">
      <div class="head-left">
        <i class="bi bi-arrow-left head-back" @click="goBack"></i>
        <div class="head-titles">
          <h1 class="n-page-title">
            {{ isEdit ? '编辑智能体' : '新建智能体' }}
          </h1>
          <p class="n-page-subtitle">
            {{ isEdit ? agentName : '配置提示词与可用工具' }}
          </p>
        </div>
      </div>
      <div class="head-actions">
        <IconButton
          icon="bi-save"
          title="保存草稿"
          :loading="savingDraft"
          @click="saveDraft"
        />
        <IconButton
          icon="bi-cloud-arrow-up"
          variant="primary"
          title="发布"
          :loading="savingPublish"
          @click="savePublished"
        />
      </div>
    </div>

    <!-- 左右两栏 -->
    <div class="panes">
      <!-- 左:名称 + 提示词 -->
      <section class="pane pane-left">
        <label class="field">
          <span class="field-label">名称</span>
          <el-input
            v-model="form.name"
            placeholder="例如:Supervisor"
            class="name-input"
          />
        </label>

        <label class="field field-grow">
          <span class="field-label">提示词 (System Prompt)</span>
          <el-input
            v-model="form.system_prompt"
            type="textarea"
            :rows="20"
            resize="none"
            placeholder="描述角色、职责与工作方式"
            class="prompt-input"
          />
        </label>
      </section>

      <!-- 右:工具选择 -->
      <section class="pane pane-right">
        <div class="field-head">
          <span class="field-label">工具</span>
          <IconButton
            small
            icon="bi-plus-lg"
            variant="primary"
            title="选择工具"
            @click="pickerVisible = true"
          />
        </div>

        <div class="tool-list">
          <div v-for="t in boundTools" :key="t.id" class="bound-tool">
            <div class="bound-body">
              <span class="bound-name">{{ t.display_name || t.name }}</span>
              <span class="bound-desc">{{ t.description || t.name }}</span>
            </div>
            <el-tooltip content="移除" placement="top" effect="dark">
              <i
                class="bi bi-x-lg bound-remove"
                @click="removeTool(t.id)"
              ></i>
            </el-tooltip>
          </div>

          <p v-if="!boundTools.length" class="tool-empty">
            还没有绑定工具。点右上角「选择」挑选这个智能体可用的工具。
          </p>
        </div>
      </section>
    </div>

    <ToolPicker
      v-model:visible="pickerVisible"
      :tools="tools"
      :model-value="form.tool_ids"
      @confirm="onPick"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import IconButton from '../components/IconButton.vue'
import ToolPicker from '../components/ToolPicker.vue'
import { createAgent, getAgent, updateAgent } from '../api/agents'
import { listTools } from '../api/tools'
import { useRoute } from '../router'

const { path, navigate } = useRoute()

const agentId = computed(() => {
  const parts = path.value.split('/').filter(Boolean)
  // /agents/new 是「新建」,不是 id 为 "new" 的编辑
  if (parts.length >= 2 && parts[1] !== 'new') return parts[1]
  return null
})
const isEdit = computed(() => !!agentId.value)

const tools = ref([])
const pickerVisible = ref(false)
const savingDraft = ref(false)
const savingPublish = ref(false)
const agentName = ref('')

const form = ref({
  name: '',
  system_prompt: '',
  tool_ids: [],
})

onMounted(async () => {
  try {
    tools.value = await listTools()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载工具失败')
  }
  if (!isEdit.value) return
  try {
    const a = await getAgent(agentId.value)
    agentName.value = a.name
    form.value = {
      name: a.name,
      system_prompt: a.draft_config?.system_prompt || '',
      tool_ids: [...(a.draft_config?.tool_ids || [])],
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载智能体失败')
  }
})

const boundTools = computed(() =>
  form.value.tool_ids
    .map((id) => tools.value.find((t) => t.id === id))
    .filter(Boolean),
)

function onPick(ids) {
  form.value.tool_ids = ids
}

function removeTool(id) {
  form.value.tool_ids = form.value.tool_ids.filter((x) => x !== id)
}

function goBack() {
  navigate('/agents')
}

function validate() {
  if (!form.value.name.trim()) {
    ElMessage.warning('名称不能为空')
    return false
  }
  return true
}

/** 保存草稿:只写 draft_config,不影响市场展示。 */
async function saveDraft() {
  if (!validate()) return
  savingDraft.value = true
  try {
    const payload = {
      name: form.value.name,
      draft_config: {
        system_prompt: form.value.system_prompt,
        tool_ids: form.value.tool_ids,
      },
    }
    if (isEdit.value) {
      await updateAgent(agentId.value, payload)
    } else {
      const created = await createAgent(payload)
      navigate(`/agents/${created.id}`, { replace: true })
    }
    ElMessage.success('草稿已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingDraft.value = false
  }
}

/**
 * 发布:把当前配置写进 published_config 并置 published=true。
 * 市场卡片展示的就是这份发布配置。
 */
async function savePublished() {
  if (!validate()) return
  savingPublish.value = true
  try {
    const config = {
      system_prompt: form.value.system_prompt,
      tool_ids: form.value.tool_ids,
    }
    const payload = {
      name: form.value.name,
      draft_config: config,
      published_config: config,
      published: true,
    }
    if (isEdit.value) {
      await updateAgent(agentId.value, payload)
    } else {
      const created = await createAgent(payload)
      navigate(`/agents/${created.id}`, { replace: true })
    }
    ElMessage.success('已发布')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '发布失败')
  } finally {
    savingPublish.value = false
  }
}
</script>

<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: var(--n-gap-lg);
  gap: var(--n-gap-md);
}

.editor-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--n-gap-md);
  flex-shrink: 0;
}
.head-left {
  display: flex;
  align-items: flex-start;
  gap: var(--n-gap);
}
.head-back {
  font-size: 18px;
  cursor: pointer;
  color: var(--n-text-secondary);
  margin-top: 4px;
}
.head-back:hover {
  color: var(--n-text);
}
.head-titles {
  min-width: 0;
}
.head-actions {
  display: flex;
  gap: var(--n-gap-sm);
  flex-shrink: 0;
}

.panes {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 1fr);
  gap: var(--n-gap-md);
  flex: 1;
  min-height: 0;
}

.pane {
  display: flex;
  flex-direction: column;
  gap: var(--n-gap-md);
  padding: var(--n-gap-md);
  background: var(--n-bg-card);
  border: 1px solid var(--n-border);
  border-radius: var(--n-radius-lg);
  min-height: 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--n-gap-xs);
  flex-shrink: 0;
}
.field-grow {
  flex: 1;
  min-height: 0;
}
.field-label {
  font-size: var(--n-text-xs);
  font-weight: 600;
  color: var(--n-text-secondary);
}
.field-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.name-input {
  font-size: var(--n-text-md);
}
.prompt-input {
  flex: 1;
}
.prompt-input :deep(.el-textarea__inner) {
  height: 100%;
  font-family: var(--n-font-mono);
  font-size: var(--n-text-sm);
  line-height: 1.6;
}

.tool-list {
  display: flex;
  flex-direction: column;
  gap: var(--n-gap-xs);
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
.bound-tool {
  display: flex;
  align-items: center;
  gap: var(--n-gap-sm);
  padding: var(--n-gap-sm);
  border: 1px solid var(--n-border-light);
  border-radius: var(--n-radius);
}
.bound-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  flex: 1;
  min-width: 0;
}
.bound-name {
  font-size: var(--n-text-sm);
  color: var(--n-text);
  font-weight: 500;
}
.bound-desc {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bound-remove {
  cursor: pointer;
  color: var(--n-text-tertiary);
  font-size: 14px;
  flex-shrink: 0;
}
.bound-remove:hover {
  color: var(--n-red);
}
.tool-empty {
  margin: 0;
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  line-height: 1.6;
}

@media (max-width: 900px) {
  .panes {
    grid-template-columns: 1fr;
  }
}
</style>
