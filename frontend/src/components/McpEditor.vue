<template>
  <el-dialog
    :model-value="visible"
    :title="isEdit ? '编辑 MCP' : '新增 MCP'"
    width="560px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      @submit.prevent
    >
      <el-form-item label="MCP 名称" prop="name">
        <el-input v-model="form.name" placeholder="例如:minimax-coding-plan-mcp" />
        <p class="hint">唯一标识,连接时用它做 server 名。</p>
      </el-form-item>

      <el-form-item label="传输方式" prop="transport">
        <el-select v-model="form.transport" placeholder="请选择传输方式">
          <el-option label="stdio" value="stdio" />
          <el-option label="Streamable HTTP" value="streamable_http" />
        </el-select>
      </el-form-item>

      <!-- ---------- stdio:本地子进程 ---------- -->
      <template v-if="form.transport === 'stdio'">
        <el-form-item label="命令" prop="command">
          <el-input v-model="form.command" placeholder="例如:uvx" />
        </el-form-item>

        <el-form-item label="参数">
          <el-input
            v-model="form.argsText"
            type="textarea"
            :rows="3"
            placeholder="每行一个参数,例如:&#10;--from&#10;minimax-coding-plan-mcp"
          />
          <p class="hint">一行一个参数;也可以整行用空格分隔。</p>
        </el-form-item>

        <el-form-item label="环境变量">
          <el-input
            v-model="form.envText"
            type="textarea"
            :rows="3"
            placeholder="每行一个 KEY=VALUE,例如:&#10;MINIMAX_API_KEY=${LLM_API_KEY}"
          />
          <p class="hint">
            密钥不要写明文,用 <code>${ENV_NAME}</code> 引用环境变量,连接时才取值。
          </p>
        </el-form-item>
      </template>

      <!-- ---------- streamable_http:HTTP 端点 ---------- -->
      <template v-else>
        <el-form-item label="URL" prop="url">
          <el-input
            v-model="form.url"
            placeholder="https://example.com/mcp"
          />
        </el-form-item>

        <el-form-item label="请求头">
          <el-input
            v-model="form.headersText"
            type="textarea"
            :rows="3"
            placeholder="每行一个 KEY=VALUE,例如:&#10;Authorization=${MCP_TOKEN}"
          />
          <p class="hint">同样用 <code>${ENV_NAME}</code> 引用,不存明文密钥。</p>
        </el-form-item>
      </template>

      <el-form-item label="启用">
        <el-switch v-model="form.enabled" active-text="启用该 MCP" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createMcpServer, updateMcpServer } from '../api/mcp'

const props = defineProps({
  visible: { type: Boolean, default: false },
  server: { type: Object, default: null },
})
const emit = defineEmits(['update:visible', 'saved'])

const formRef = ref(null)
const saving = ref(false)
const isEdit = computed(() => !!props.server?.id)
const form = ref(blank())

function blank() {
  return {
    name: '',
    transport: 'stdio',
    command: '',
    argsText: '',
    envText: '',
    url: '',
    headersText: '',
    enabled: true,
  }
}

const rules = computed(() => ({
  name: [{ required: true, message: '请填写 MCP 名称', trigger: 'blur' }],
  command:
    form.value.transport === 'stdio'
      ? [{ required: true, message: '请填写命令', trigger: 'blur' }]
      : [],
  url:
    form.value.transport === 'streamable_http'
      ? [
          { required: true, message: '请填写 URL', trigger: 'blur' },
          {
            pattern: /^https?:\/\/.+/,
            message: 'URL 要以 http:// 或 https:// 开头',
            trigger: 'blur',
          },
        ]
      : [],
}))

/** "a b c" 或 "a\nb\nc" → ['a','b','c'] */
function parseList(text) {
  if (!text) return []
  return text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .flatMap((l) => (l.includes(' ') ? l.split(/\s+/) : [l]))
}

function parseKV(text) {
  const out = {}
  for (const line of (text || '').split('\n')) {
    const t = line.trim()
    if (!t) continue
    const i = t.indexOf('=')
    if (i <= 0) continue
    out[t.slice(0, i).trim()] = t.slice(i + 1).trim()
  }
  return out
}

watch(
  () => props.visible,
  (v) => {
    if (!v) return
    const cfg = props.server?.config || {}
    form.value = props.server
      ? {
          name: props.server.name,
          transport: props.server.transport || 'stdio',
          command: cfg.command || '',
          argsText: (cfg.args || []).join('\n'),
          envText: Object.entries(cfg.env || {})
            .map(([k, v]) => `${k}=${v}`)
            .join('\n'),
          url: cfg.url || '',
          headersText: Object.entries(cfg.headers || {})
            .map(([k, v]) => `${k}=${v}`)
            .join('\n'),
          enabled: !!props.server.enabled,
        }
      : blank()
    formRef.value?.clearValidate()
  },
  { immediate: true },
)

function buildConfig() {
  if (form.value.transport === 'streamable_http') {
    const headers = parseKV(form.value.headersText)
    const cfg = { url: form.value.url.trim() }
    if (Object.keys(headers).length) cfg.headers = headers
    return cfg
  }
  const env = parseKV(form.value.envText)
  const cfg = { command: form.value.command.trim() }
  const args = parseList(form.value.argsText)
  if (args.length) cfg.args = args
  if (Object.keys(env).length) cfg.env = env
  return cfg
}

async function save() {
  const ok = await formRef.value
    ?.validate()
    .catch(() => false)
  if (!ok) return

  saving.value = true
  try {
    const payload = {
      name: form.value.name.trim(),
      transport: form.value.transport,
      config: buildConfig(),
      enabled: form.value.enabled,
    }
    if (isEdit.value) {
      await updateMcpServer(props.server.id, payload)
    } else {
      await createMcpServer(payload)
    }
    ElMessage.success('已保存')
    emit('update:visible', false)
    emit('saved')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.hint {
  margin: 4px 0 0;
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
}
code {
  background: var(--n-bg-code);
  padding: 1px 5px;
  border-radius: var(--n-radius-sm);
  font-family: var(--n-font-mono);
}
</style>
