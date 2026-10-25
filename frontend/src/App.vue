<template>
  <AppShell>
    <component :is="currentView" />
  </AppShell>
</template>

<script setup>
import { computed } from 'vue'
import AppShell from './components/AppShell.vue'
import ChatView from './views/ChatView.vue'
import MarketView from './views/MarketView.vue'
import AgentsView from './views/AgentsView.vue'
import AgentEditorView from './views/AgentEditorView.vue'
import ToolsView from './views/ToolsView.vue'
import ModelsView from './views/ModelsView.vue'
import McpView from './views/McpView.vue'
import { matchRoute, useRoute } from './router'

const { path } = useRoute()

const routes = {
  '/chat': ChatView,
  '/market': MarketView,
  '/agents': AgentsView,
  '/tools': ToolsView,
  '/models': ModelsView,
  '/mcp': McpView,
}

const currentView = computed(() => {
  // 智能体编辑页:/agents/new 和 /agents/:id
  if (path.value === '/agents/new') return AgentEditorView
  if (matchRoute('/agents/:id', path.value)) return AgentEditorView
  // 会话页:/chat/:id(没有 id 时是新对话页,同一个组件里判断)
  if (matchRoute('/chat/:id', path.value)) return ChatView
  return routes[path.value] || ChatView
})
</script>
