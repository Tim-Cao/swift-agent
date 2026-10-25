<template>
  <div class="n-page">
    <div class="page-head">
      <div>
        <h1 class="n-page-title">智能体管理</h1>
      </div>
      <div class="head-actions">
        <IconButton
          icon="bi-plus-lg"
          variant="primary"
          title="新建智能体"
          @click="createNew"
        />
      </div>
    </div>

    <CardGrid
      :items="agents"
      :empty-text="loading ? '加载中…' : '还没有智能体'"
      :title-of="titleOf"
      :desc-of="descOf"
      :key-of="keyOf"
      @select="openEditor"
    >
      <template #icon>
        <i class="bi bi-robot"></i>
      </template>
      <template #status="{ item }">
        <el-tag size="small" effect="plain">智能体</el-tag>
        <el-tag
          :type="item.published ? 'success' : 'info'"
          size="small"
          effect="plain"
        >
          {{ item.published ? '已发布' : '草稿' }}
        </el-tag>
      </template>
      <template #actions="{ item }">
        <IconButton
          small
          :icon="item.published ? 'bi-power' : 'bi-power'"
          variant="danger"
          :title="item.published ? '停用' : '启用'"
          @click="togglePublish(item)"
        />
        <IconButton
          small
          icon="bi-pencil"
          title="编辑"
          @click="openEditor(item)"
        />
        <IconButton
          small
          icon="bi-trash"
          variant="danger"
          title="删除"
          @click="remove(item)"
        />
      </template>
      <template #footer="{ item }">
        <span class="meta">
          {{ item.draft_config?.tool_ids?.length || 0 }} 个工具
        </span>
        <el-tag v-if="item.is_default" size="small" type="info" effect="plain">
          默认
        </el-tag>
      </template>
    </CardGrid>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import CardGrid from '../components/CardGrid.vue'
import IconButton from '../components/IconButton.vue'
import { deleteAgent, listAgents, updateAgent } from '../api/agents'
import { useRoute } from '../router'

const { navigate } = useRoute()
const agents = ref([])
const loading = ref(true)

onMounted(load)

async function load() {
  loading.value = true
  try {
    agents.value = await listAgents()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载智能体失败')
  } finally {
    loading.value = false
  }
}

function titleOf(a) {
  return a.name
}
/** 卡片描述 = 草稿配置里的提示词首行 */
function descOf(a) {
  const prompt = a.draft_config?.system_prompt || ''
  const first = prompt.split('\n').find((l) => l.trim())
  return first || '还没有写提示词'
}
function keyOf(a) {
  return a.id
}

function openEditor(a) {
  navigate(`/agents/${a.id}`)
}

function createNew() {
  navigate('/agents/new')
}

/** 启用 / 停用:停用就是从市场下架(取消发布) */
async function togglePublish(a) {
  try {
    if (a.published) {
      await updateAgent(a.id, { published: false })
      ElMessage.success('已停用')
    } else {
      // 启用 = 把草稿配置复制成发布配置
      await updateAgent(a.id, {
        published: true,
        published_config: a.draft_config,
      })
      ElMessage.success('已启用')
    }
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

async function remove(a) {
  try {
    await ElMessageBox.confirm(`确定删除智能体「${a.name}」?`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteAgent(a.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--n-gap-md);
}
.head-actions {
  display: flex;
  gap: var(--n-gap-sm);
  flex-shrink: 0;
}
.meta {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
}
</style>
