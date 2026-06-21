<template>
  <el-container class="layout">
    <el-aside width="260px" class="aside">
      <SessionList
        :sessions="store.sessions"
        :current-id="store.currentId"
        @select="onSelect"
        @remove="onRemove"
        @new="onNew"
      />
    </el-aside>
    <el-main class="main">
      <ChatWindow
        :messages="store.messages"
        :session-id="store.currentId"
        @appendMessage="appendLocal"
      />
    </el-main>
  </el-container>
</template>

<script setup>
import { onMounted } from 'vue'
import { useSessionStore } from '../stores/session'
import SessionList from '../components/SessionList.vue'
import ChatWindow from '../components/ChatWindow.vue'

const store = useSessionStore()

onMounted(async () => {
  await store.loadSessions()
})

async function onSelect(id) {
  await store.selectSession(id)
}

async function onRemove(id) {
  await store.removeSession(id)
}

async function onNew() {
  const s = await store.newSession()
  // 后端会返回新 session id;选中后,首条用户消息将触发自动重命名
  return s
}

function appendLocal(msg) {
  // 临时展示消息(后端最终会通过 list_messages 返回完整记录)
  store.pushMessage(msg)
}
</script>

<style scoped>
.layout { height: 100vh; }
.aside { background: #f5f7fa; border-right: 1px solid #e6e8eb; padding: 0; }
.main { padding: 0; }
</style>
