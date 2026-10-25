<template>
  <AppShell>
    <component :is="currentView" />
  </AppShell>
</template>

<script setup>
import { computed } from 'vue'
import AppShell from './components/AppShell.vue'
import ChatView from './views/ChatView.vue'
import ToolsView from './views/ToolsView.vue'
import { matchRoute, useRoute } from './router'

const { path } = useRoute()

const routes = {
  '/chat': ChatView,
  '/tools': ToolsView,
}

const currentView = computed(() => {
  // 会话页:/chat/:id(没有 id 时是新对话页,同一个组件里判断)
  if (matchRoute('/chat/:id', path.value)) return ChatView
  return routes[path.value] || ChatView
})
</script>
