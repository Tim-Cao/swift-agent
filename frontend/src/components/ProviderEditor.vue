<template>
  <el-dialog
    :model-value="visible"
    :title="isEdit ? '编辑提供商' : '新增提供商'"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      @submit.prevent
    >
      <el-form-item label="提供商名称" prop="name">
        <el-input v-model="form.name" placeholder="例如:MiniMax" />
      </el-form-item>

      <el-form-item label="提供商 ID" prop="slug">
        <el-input
          v-model="form.slug"
          placeholder="例如:minimax"
          :disabled="isEdit && slugLocked"
        />
        <p class="hint">
          唯一标识,只能用小写字母、数字、短横线(如 <code>minimax</code>)。
        </p>
      </el-form-item>

      <el-form-item label="Base URL" prop="base_url">
        <el-input
          v-model="form.base_url"
          placeholder="https://api.openai.com/v1"
        />
        <p class="hint">服务的 Base URL;后端会自动补全 /models 路径。</p>
      </el-form-item>

      <el-form-item label="API 密钥" prop="api_key">
        <el-input
          v-model="form.api_key"
          type="password"
          show-password
          :placeholder="isEdit ? '留空表示不修改' : 'sk-…'"
        />
        <p v-if="isEdit" class="hint">当前:{{ provider?.api_key || '(未设置)' }}</p>
      </el-form-item>

      <el-form-item label="启用">
        <el-switch v-model="form.enabled" active-text="启用该提供商" />
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
import { createProvider, updateProvider } from '../api/models'

const props = defineProps({
  visible: { type: Boolean, default: false },
  provider: { type: Object, default: null },
})
const emit = defineEmits(['update:visible', 'saved'])

const formRef = ref(null)
const saving = ref(false)
const isEdit = computed(() => !!props.provider?.id)
// 已有 ID 的提供商不允许改 ID —— 改了会跟别处(配置、脚本)里引用的 ID 对不上
const slugLocked = computed(() => isEdit.value && !!props.provider?.slug)
const form = ref(blank())

function blank() {
  return { name: '', slug: '', base_url: '', api_key: '', enabled: true }
}

/**
 * 表单校验规则。
 *
 * API 密钥在**新增**时必填,在**编辑**时留空表示"不修改" —— 所以编辑时不校验它,
 * 否则用户只想改个名字也得重新输一遍密钥。
 */
const rules = computed(() => ({
  name: [{ required: true, message: '请填写提供商名称', trigger: 'blur' }],
  slug: [
    { required: true, message: '请填写提供商 ID', trigger: 'blur' },
    {
      pattern: /^[\w-]+$/,
      message: '只能包含小写字母、数字、下划线和短横线',
      trigger: 'blur',
    },
  ],
  base_url: [
    { required: true, message: '请填写 Base URL', trigger: 'blur' },
    {
      pattern: /^https?:\/\/.+/,
      message: 'Base URL 要以 http:// 或 https:// 开头',
      trigger: 'blur',
    },
  ],
  api_key: isEdit.value
    ? []
    : [{ required: true, message: '请填写 API 密钥', trigger: 'blur' }],
}))

watch(
  () => props.visible,
  (v) => {
    if (!v) return
    form.value = props.provider
      ? {
          name: props.provider.name,
          slug: props.provider.slug || '',
          base_url: props.provider.base_url,
          api_key: '',
          enabled: !!props.provider.enabled,
        }
      : blank()
    // 打开时清掉上一轮的校验红字
    formRef.value?.clearValidate()
  },
  { immediate: true },
)

async function save() {
  const ok = await formRef.value
    ?.validate()
    .catch(() => false)
  if (!ok) return

  saving.value = true
  try {
    if (isEdit.value) {
      const payload = {
        name: form.value.name,
        base_url: form.value.base_url,
        enabled: form.value.enabled,
      }
      // 留空 = 不修改;后端也会忽略掩码值
      if (form.value.api_key) payload.api_key = form.value.api_key
      if (!slugLocked.value && form.value.slug.trim()) {
        payload.slug = form.value.slug.trim()
      }
      await updateProvider(props.provider.id, payload)
    } else {
      await createProvider({ ...form.value })
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
