<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': collapsed }">
    <!-- 左侧导航 -->
    <aside class="sidebar">
      <div class="brand">
        <i class="bi bi-command brand-mark"></i>
        <span class="brand-name">Swift Agent</span>
      </div>

      <nav class="nav">
        <!-- 主菜单:没有父级分组 -->
        <a
          v-for="item in topItems"
          :key="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
          :title="item.label"
          @click="go(item.path)"
        >
          <i class="bi nav-icon" :class="item.icon"></i>
          <span class="nav-text">{{ item.label }}</span>
        </a>

        <!-- 更多:默认收缩 -->
        <button
          type="button"
          class="nav-toggle"
          :class="{ open: moreOpen }"
          :aria-expanded="moreOpen"
          @click="moreOpen = !moreOpen"
        >
          <span class="nav-toggle-label">更多</span>
          <i class="bi nav-caret" :class="moreOpen ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
        </button>
        <div v-show="moreOpen" class="nav-sub">
          <a
            v-for="item in moreItems"
            :key="item.path"
            class="nav-item nav-item-sub"
            :class="{ active: isActive(item.path) }"
            :title="item.label"
            @click="go(item.path)"
          >
            <i class="bi nav-icon" :class="item.icon"></i>
            <span class="nav-text">{{ item.label }}</span>
          </a>
        </div>
      </nav>

      <!-- 最近:主菜单最下方 -->
      <div class="history">
        <div class="history-head">
          <span class="history-label">最近</span>
        </div>
        <SessionList
          :sessions="store.sessions"
          :current-id="store.currentId"
          @select="onSelectSession"
          @remove="onRemoveSession"
        />
      </div>

      <div class="sidebar-foot">
        <span class="dot"></span>
        <span class="foot-text">本地服务</span>
      </div>
    </aside>

    <!-- 主内容 -->
    <main class="content">
      <!-- 顶部工具条:侧边栏展开/收起按钮独占一行,
           和下面的正文之间有一条分割线。 -->
      <div class="content-bar">
        <el-tooltip
          :content="collapsed ? '展开侧边栏' : '收起侧边栏'"
          placement="bottom"
          effect="dark"
        >
          <button
            type="button"
            class="collapse-btn"
            :aria-expanded="!collapsed"
            :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
            @click="collapsed = !collapsed"
          >
            <i class="bi bi-layout-sidebar"></i>
          </button>
        </el-tooltip>
      </div>

      <div class="content-body">
        <slot />
      </div>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import SessionList from './SessionList.vue'
import { useSessionStore } from '../stores/session'
import { useRoute } from '../router'

const store = useSessionStore()
const { path, navigate } = useRoute()

/** 「更多」分组默认收缩 */
const moreOpen = ref(false)
/** 侧边栏整体收起(只留图标条) */
const collapsed = ref(false)

// 主菜单(无父级)
const topItems = [
  { path: '/chat', label: '新对话', icon: 'bi-pencil-square' },
  { path: '/market', label: '智能体市场', icon: 'bi-shop' },
]

// 「更多」分组(默认收缩)
const moreItems = [
  { path: '/agents', label: '智能体管理', icon: 'bi-robot' },
  { path: '/tools', label: '工具管理', icon: 'bi-tools' },
  { path: '/models', label: '模型管理', icon: 'bi-cpu' },
  { path: '/mcp', label: 'MCP 管理', icon: 'bi-plug' },
]

onMounted(async () => {
  // 历史会话在侧边栏展示,数据由这里统一加载
  try {
    await store.loadSessions()
  } catch {
    /* 加载失败不挡页面 */
  }
})

/** 当前激活项:前缀匹配,保证 /agents/xxx 时 '智能体管理' 仍高亮 */
function isActive(p) {
  if (p === '/chat') return path.value === '/chat' || path.value.startsWith('/chat/')
  return path.value === p || path.value.startsWith(`${p}/`)
}

function go(p) {
  navigate(p)
}

function onSelectSession(id) {
  navigate(`/chat/${id}`)
}

async function onRemoveSession(id) {
  await store.removeSession(id)
}

defineExpose({ go })
</script>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  width: 248px;
  flex-shrink: 0;
  background: var(--n-bg-sidebar);
  border-right: 1px solid var(--n-border);
  display: flex;
  flex-direction: column;
  padding: var(--n-gap-md) var(--n-gap-sm) var(--n-gap-sm);
  transition: width 0.16s ease;
  overflow: hidden;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--n-gap-sm);
  padding: var(--n-gap-xs) var(--n-gap-sm) var(--n-gap-md);
}

/* 应用图标 + 名称:用品牌色,跟正文区分开 */
.brand-mark {
  color: var(--n-accent);
  font-size: 15px;
}

.brand-name {
  font-weight: 700;
  font-size: var(--n-text-md);
  letter-spacing: -0.01em;
  color: var(--n-accent);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 顶部工具条:侧边栏展开/收起按钮独占一行。
   之前这个按钮是绝对定位浮在内容区左上角的,跟「智能体编辑页」的
   返回箭头会叠在一起(两个图标都在左上角)。改成独立的行 + 分割线,
   位置冲突就不存在了。 */
.content-bar {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  height: 44px;
  padding: 0 var(--n-gap-md);
  background: var(--n-bg);
  border-bottom: 1px solid var(--n-border);
}

/* 收起 / 展开侧边栏 */
.collapse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border: 1px solid transparent;
  border-radius: var(--n-radius);
  background: transparent;
  color: var(--n-text-tertiary);
  cursor: pointer;
  font-size: 15px;
  transition:
    background-color 0.12s ease,
    border-color 0.12s ease,
    color 0.12s ease;
}
.collapse-btn:hover {
  background: var(--n-bg-hover);
  border-color: var(--n-border);
  color: var(--n-text);
}

/* 收起态:只留图标条 */
.sidebar-collapsed .sidebar {
  width: 56px;
}
.sidebar-collapsed .brand {
  flex-direction: column;
  gap: var(--n-gap-xs);
  padding: var(--n-gap-xs) 0 var(--n-gap-md);
}
.sidebar-collapsed .brand-mark {
  font-size: 17px;
}
.sidebar-collapsed .brand-name,
.sidebar-collapsed .nav-text,
.sidebar-collapsed .nav-toggle-label,
.sidebar-collapsed .nav-caret,
.sidebar-collapsed .history-label,
.sidebar-collapsed .foot-text,
.sidebar-collapsed .session-list {
  display: none;
}
.sidebar-collapsed .collapse-btn {
  /* 图标方向跟着侧边栏状态翻转(收起时指向右边) */
  transform: scaleX(-1);
}
.sidebar-collapsed .nav-item,
.sidebar-collapsed .nav-toggle {
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
}
.sidebar-collapsed .nav-toggle {
  display: none;
}
.sidebar-collapsed .nav-sub {
  padding-left: 0;
}
.sidebar-collapsed .history {
  border-top-color: var(--n-border-light);
}
.sidebar-collapsed .sidebar-foot {
  justify-content: center;
}

.nav {
  flex-shrink: 0;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--n-gap-sm);
  padding: 5px var(--n-gap-sm);
  border-radius: var(--n-radius);
  color: var(--n-text-secondary);
  font-size: var(--n-text-sm);
  cursor: pointer;
  user-select: none;
  transition:
    background-color 0.1s ease,
    color 0.1s ease;
}

.nav-item:hover {
  background: var(--n-bg-hover);
  color: var(--n-text);
  text-decoration: none;
}

.nav-item.active {
  background: var(--n-bg-active);
  color: var(--n-text);
  font-weight: 500;
}

.nav-icon {
  font-size: 14px;
  width: 18px;
  text-align: center;
  flex-shrink: 0;
}

.nav-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 「更多」分组:可折叠,默认收缩 */
.nav-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-top: var(--n-gap-xs);
  padding: 5px var(--n-gap-sm);
  border: none;
  border-radius: var(--n-radius);
  background: transparent;
  color: var(--n-text-secondary);
  font-family: inherit;
  font-size: var(--n-text-xs);
  font-weight: 600;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition:
    background-color 0.1s ease,
    color 0.1s ease;
}
.nav-toggle:hover {
  background: var(--n-bg-hover);
  color: var(--n-text);
}
.nav-caret {
  font-size: 11px;
  opacity: 0.6;
}
.nav-sub {
  padding-left: var(--n-gap-sm);
  margin-bottom: var(--n-gap-xs);
}
/* 子项缩进一点,视觉上从属于「更多」 */
.nav-item-sub {
  font-size: var(--n-text-sm);
}

/* 历史会话:主菜单最下方 */
.history {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  margin-top: var(--n-gap-md);
  border-top: 1px solid var(--n-border-light);
  padding-top: var(--n-gap-sm);
}

.history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--n-gap-sm) var(--n-gap-xs);
}

.history-label {
  font-size: var(--n-text-xs);
  font-weight: 600;
  color: var(--n-text-tertiary);
  letter-spacing: 0.02em;
}

.sidebar-foot {
  display: flex;
  align-items: center;
  gap: var(--n-gap-sm);
  padding: var(--n-gap-sm) var(--n-gap-sm) 0;
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  border-top: 1px solid var(--n-border-light);
  flex-shrink: 0;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--n-green);
}

.content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--n-bg);
}

/* 正文:占满剩下的高度,自己滚动(工具条固定在顶部不动) */
.content-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
