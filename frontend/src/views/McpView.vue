<template>
  <div class="n-page">
    <div class="page-head">
      <div>
        <h1 class="n-page-title">MCP 管理</h1>
      </div>
      <div class="head-actions">
        <IconButton
          icon="bi-plus-lg"
          variant="primary"
          title="新增 MCP"
          @click="openEditor()"
        />
      </div>
    </div>

    <CardGrid
      :items="servers"
      :empty-text="loading ? '加载中…' : '还没有 MCP 服务端'"
      :title-of="(m) => m.name"
      :desc-of="descOf"
      :key-of="(m) => m.id"
      @select="openDetails"
    >
      <template #icon>
        <i class="bi bi-plug"></i>
      </template>
      <template #status="{ item }">
        <el-tag size="small" effect="plain">MCP</el-tag>
        <el-tag :type="statusType(item.status)" size="small" effect="plain">
          {{ statusLabel(item.status) }}
        </el-tag>
      </template>
      <template #actions="{ item }">
        <IconButton
          small
          icon="bi-pencil"
          title="编辑"
          @click="openEditor(item)"
        />
        <IconButton
          small
          icon="bi-lightning-charge"
          title="测试连接"
          @click="test(item)"
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
        <span class="meta">传输方式:{{ item.transport_label || item.transport }}</span>
        <span class="meta">{{ item.tool_names?.length || 0 }} 个工具</span>
        <el-tag v-if="!item.enabled" size="small" type="info" effect="plain">
          已停用
        </el-tag>
      </template>
    </CardGrid>

    <McpDetails
      v-model:visible="detailsVisible"
      :server="detailing"
      @edit="editFromDetails"
      @synced="load"
    />
    <McpEditor v-model:visible="editorVisible" :server="editing" @saved="load" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import CardGrid from '../components/CardGrid.vue'
import IconButton from '../components/IconButton.vue'
import McpDetails from '../components/McpDetails.vue'
import McpEditor from '../components/McpEditor.vue'
import {
  deleteMcpServer,
  listMcpServers,
  testMcpServer,
} from '../api/mcp'

const servers = ref([])
const loading = ref(true)
const editorVisible = ref(false)
const editing = ref(null)
const detailsVisible = ref(false)
const detailing = ref(null)

onMounted(load)

async function load() {
  loading.value = true
  try {
    servers.value = await listMcpServers()
    // 详情弹窗开着的话,让它看到最新的数据(同步工具后会刷新)
    if (detailsVisible.value && detailing.value) {
      const fresh = servers.value.find((s) => s.id === detailing.value.id)
      if (fresh) detailing.value = fresh
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载 MCP 列表失败')
  } finally {
    loading.value = false
  }
}

/** 卡片描述 = 连接方式(命令 / URL) */
function descOf(m) {
  return m.description || '还没有配置连接信息'
}

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

/** 点卡片 → 进详情弹窗 */
function openDetails(m) {
  if (!m?.id) return
  detailing.value = m
  detailsVisible.value = true
}

function openEditor(m) {
  editing.value = m?.id ? m : null
  editorVisible.value = true
}

/** 详情弹窗里点「编辑」→ 关掉详情,打开编辑弹窗(两个弹窗不叠着) */
function editFromDetails() {
  if (!detailing.value?.id) return
  detailsVisible.value = false
  openEditor(detailing.value)
}

async function test(m) {
  try {
    const res = await testMcpServer(m.id)
    if (res.ok) {
      ElMessage.success(`连接成功,拿到 ${res.tools.length} 个工具`)
    } else {
      ElMessage.error(`连接失败:${res.error || '未知错误'}`)
    }
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '测试失败')
  }
}

async function remove(m) {
  try {
    await ElMessageBox.confirm(`确定删除 MCP「${m.name}」?`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteMcpServer(m.id)
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
