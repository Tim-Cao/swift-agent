<template>
  <div class="n-page">
    <h1 class="n-page-title">模型管理</h1>

    <el-tabs v-model="tab" class="tabs">
      <!-- ---------- 提供商 ---------- -->
      <el-tab-pane label="提供商" name="providers">
        <div class="pane-head">
          <IconButton
            icon="bi-plus-lg"
            variant="primary"
            title="新增提供商"
            @click="openProvider()"
          />
        </div>

        <CardGrid
          :items="providers"
          :empty-text="loading ? '加载中…' : '还没有提供商'"
          :title-of="(p) => p.name"
          :desc-of="providerDesc"
          :key-of="(p) => p.id"
          @select="openProvider"
        >
          <template #icon>
            <i class="bi bi-plug"></i>
          </template>
          <template #status="{ item }">
            <el-tag size="small" effect="plain">提供商</el-tag>
            <el-tag
              :type="item.enabled ? 'success' : 'info'"
              size="small"
              effect="plain"
            >
              {{ item.enabled ? '已启用' : '已停用' }}
            </el-tag>
          </template>
          <template #actions="{ item }">
            <IconButton
              small
              icon="bi-search"
              title="发现模型"
              @click="discover(item)"
            />
            <IconButton
              small
              icon="bi-pencil"
              title="编辑"
              @click="openProvider(item)"
            />
            <IconButton
              small
              icon="bi-trash"
              variant="danger"
              title="删除"
              @click="removeProvider(item)"
            />
          </template>
          <template #footer="{ item }">
            <span class="meta">{{ item.base_url }}</span>
            <span class="meta">{{ item.model_ids?.length || 0 }} 个模型</span>
          </template>
        </CardGrid>
      </el-tab-pane>

      <!-- ---------- 模型 ---------- -->
      <el-tab-pane label="模型" name="models">
        <CardGrid
          :items="models"
          :empty-text="loading ? '加载中…' : '还没有模型,请先在提供商页发现模型'"
          :title-of="modelTitle"
          :desc-of="modelDesc"
          :key-of="(m) => m.id"
          @select="toggleDefault"
        >
          <template #icon>
            <i class="bi bi-cpu"></i>
          </template>
          <template #status="{ item }">
            <el-tag size="small" effect="plain">模型</el-tag>
            <el-tag v-if="item.is_default" size="small" type="success" effect="plain">
              默认
            </el-tag>
          </template>
          <template #actions="{ item }">
            <IconButton
              small
              :icon="item.is_default ? 'bi-star-fill' : 'bi-star'"
              :title="item.is_default ? '取消默认' : '设为默认'"
              @click="toggleDefault(item)"
            />
          </template>
          <template #footer="{ item }">
            <span class="meta">提供商:{{ providerName(item.provider_id) }}</span>
          </template>
        </CardGrid>
      </el-tab-pane>
    </el-tabs>

    <ProviderEditor
      v-model:visible="providerVisible"
      :provider="editingProvider"
      @saved="load"
    />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import CardGrid from '../components/CardGrid.vue'
import IconButton from '../components/IconButton.vue'
import ProviderEditor from '../components/ProviderEditor.vue'
import {
  deleteProvider,
  discoverModels,
  listModels,
  listProviders,
  setDefaultModel,
  unsetDefaultModel,
} from '../api/models'

const tab = ref('providers')
const providers = ref([])
const models = ref([])
const loading = ref(true)
const providerVisible = ref(false)
const editingProvider = ref(null)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const [p, m] = await Promise.all([listProviders(), listModels()])
    providers.value = p
    models.value = m
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function providerDesc(p) {
  // 卡片不显示 API Key,也不显示"OpenAI 兼容端点"这种实现细节 —— 只给标识
  return p.slug ? `提供商 ID:${p.slug}` : '未设置提供商 ID'
}

function providerName(id) {
  return providers.value.find((p) => p.id === id)?.name || id
}

function modelTitle(m) {
  return m.display_name || m.id
}

function modelDesc(m) {
  return m.display_name && m.display_name !== m.id ? m.id : '点击卡片设为默认模型'
}

function openProvider(p) {
  editingProvider.value = p?.id ? p : null
  providerVisible.value = true
}

async function discover(p) {
  try {
    const res = await discoverModels(p.id)
    ElMessage.success(`发现 ${res.models.length} 个模型,新增 ${res.added} 个`)
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '发现模型失败')
  }
}

async function removeProvider(p) {
  try {
    await ElMessageBox.confirm(
      `确定删除提供商「${p.name}」?其下模型会一并删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteProvider(p.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

async function toggleDefault(m) {
  try {
    if (m.is_default) {
      await unsetDefaultModel(m.id)
      ElMessage.success('已取消默认模型')
    } else {
      await setDefaultModel(m.id)
      ElMessage.success(`已将「${m.display_name || m.id}」设为默认模型`)
    }
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}
</script>

<style scoped>
.tabs :deep(.el-tabs__item) {
  font-size: var(--n-text-sm);
}
.pane-head {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--n-gap-md);
  margin-bottom: var(--n-gap-md);
}
.pane-hint {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
}
.meta {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
}
.mono {
  font-family: var(--n-font-mono);
}
</style>
