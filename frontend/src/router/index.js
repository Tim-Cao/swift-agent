/**
 * 极简 hash 路由(不引入 vue-router 依赖)。
 *
 * 用法:
 *   const { route, navigate } = useRoute()
 *   route.path        // 当前路径,如 '/agents'
 *   route.query       // 查询参数对象
 *   navigate('/agents/xxx')  // 跳转
 *
 * 路由表在 AppShell 里通过 <component :is> 渲染。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'

// SSR / 测试环境没有 window —— 用一个内存版 hash 兜底
const hasWindow = typeof window !== 'undefined'

function currentHash() {
  return hasWindow ? window.location.hash : ''
}

const path = ref(currentHash().slice(1) || '/chat')
const query = ref({})

function parseHash() {
  const raw = currentHash().slice(1) || '/chat'
  const [p, qs] = raw.split('?')
  path.value = p || '/chat'
  const q = {}
  if (qs) {
    for (const part of qs.split('&')) {
      if (!part) continue
      const [k, v = ''] = part.split('=')
      q[decodeURIComponent(k)] = decodeURIComponent(v)
    }
  }
  query.value = q
}

function navigate(to, { replace = false } = {}) {
  const target = to.startsWith('#') ? to : `#${to}`
  if (!hasWindow) {
    path.value = target.slice(1).split('?')[0]
    return
  }
  if (replace) {
    window.history.replaceState(null, '', target)
    parseHash()
  } else {
    window.location.hash = target
  }
}

let _listeners = 0
let _bound = false

export function useRoute() {
  onMounted(() => {
    if (!_bound && hasWindow) {
      window.addEventListener('hashchange', parseHash)
      _bound = true
    }
    _listeners += 1
    parseHash()
  })
  onUnmounted(() => {
    _listeners -= 1
    if (_listeners <= 0 && _bound && hasWindow) {
      window.removeEventListener('hashchange', parseHash)
      _bound = false
    }
  })

  return {
    path: computed(() => path.value),
    query: computed(() => query.value),
    navigate,
  }
}

/** 路由路径匹配:支持 '/agents/:id' 形式 */
export function matchRoute(pattern, actual) {
  const p = pattern.split('/').filter(Boolean)
  const a = actual.split('/').filter(Boolean)
  if (p.length !== a.length) return null
  const params = {}
  for (let i = 0; i < p.length; i += 1) {
    if (p[i].startsWith(':')) {
      params[p[i].slice(1)] = decodeURIComponent(a[i])
    } else if (p[i] !== a[i]) {
      return null
    }
  }
  return params
}

export { navigate }
