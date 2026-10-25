<template>
  <div class="n-page">
    <div class="page-head">
      <div>
        <h1 class="n-page-title">工具管理</h1>
      </div>
      <div class="head-actions">
        <IconButton
          icon="bi-plus-lg"
          variant="primary"
          title="新建工具"
          @click="editorVisible = true"
        />
      </div>
    </div>

    <CardGrid
      :items="tools"
      :empty-text="loading ? '加载中…' : '还没有工具'"
      :title-of="titleOf"
      :desc-of="descOf"
      :key-of="keyOf"
      @select="onSelect"
    >
      <template #icon>
        <i class="bi bi-tools"></i>
      </template>
      <template #status="{ item }">
        <el-tag size="small" effect="plain">工具</el-tag>
        <el-tag v-if="item.builtin" size="small" type="info" effect="plain">
          内置
        </el-tag>
        <el-tag v-else size="small" effect="plain">上传</el-tag>
      </template>
      <template #actions="{ item }">
        <IconButton
          v-if="!item.builtin"
          small
          icon="bi-pencil"
          title="编辑"
          @click="edit(item)"
        />
        <IconButton
          v-if="!item.builtin"
          small
          icon="bi-trash"
          variant="danger"
          title="删除"
          @click="remove(item)"
        />
      </template>
    </CardGrid>

    <ToolEditor v-model:visible="editorVisible" :tool="editing" @saved="load" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import CardGrid from '../components/CardGrid.vue'
import IconButton from '../components/IconButton.vue'
import ToolEditor from '../components/ToolEditor.vue'
import { deleteTool, listTools } from '../api/tools'

const tools = ref([])
const loading = ref(true)
const editorVisible = ref(false)
const editing = ref(null)

onMounted(load)

async function load() {
  loading.value = true
  try {
    tools.value = await listTools()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载工具失败')
  } finally {
    loading.value = false
  }
}

function titleOf(t) {
  return t.display_name || t.name
}
function descOf(t) {
  return t.description || `工具标识:${t.name}`
}
function keyOf(t) {
  return t.id
}

function onSelect(t) {
  if (t.builtin) return
  edit(t)
}

function edit(t) {
  editing.value = t
  editorVisible.value = true
}

async function remove(t) {
  try {
    await ElMessageBox.confirm(`确定删除工具「${t.name}」?`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteTool(t.id)
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
code {
  background: var(--n-bg-code);
  padding: 1px 5px;
  border-radius: var(--n-radius-sm);
  font-family: var(--n-font-mono);
  font-size: 0.92em;
}
</style>
