<template>
  <div class="n-page">
    <h1 class="n-page-title">智能体市场</h1>

    <CardGrid
      :items="agents"
      :empty-text="loading ? '加载中…' : '暂无已发布的智能体'"
      :title-of="titleOf"
      :desc-of="descOf"
      :key-of="keyOf"
      @select="onSelect"
    >
      <template #icon>
        <i class="bi bi-robot"></i>
      </template>
      <template #status>
        <el-tag size="small" effect="plain">智能体</el-tag>
        <el-tag size="small" type="success" effect="plain">已发布</el-tag>
      </template>
      <template #footer="{ item }">
        <span class="meta">
          {{ item.published_config?.tool_ids?.length || 0 }} 个工具
        </span>
      </template>
    </CardGrid>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import CardGrid from '../components/CardGrid.vue'
import { listMarketAgents } from '../api/agents'
import { useRoute } from '../router'

const { navigate } = useRoute()
const agents = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    agents.value = await listMarketAgents()
  } finally {
    loading.value = false
  }
})

function titleOf(a) {
  return a.name
}
/** 卡片描述 = 发布配置里的提示词首行 */
function descOf(a) {
  const prompt = a.published_config?.system_prompt || ''
  const first = prompt.split('\n').find((l) => l.trim())
  return first || '这个智能体还没有写提示词。'
}
function keyOf(a) {
  return a.id
}
function onSelect(a) {
  // 带上 agent 参数 → 新对话页会先建好绑定该 agent 的会话
  navigate(`/chat?agent=${encodeURIComponent(a.id)}`)
}
</script>

<style scoped>
.meta {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
}
</style>
