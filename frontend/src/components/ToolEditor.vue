<template>
  <el-dialog
    :model-value="visible"
    :title="isEdit ? '编辑工具' : '新建工具'"
    width="560px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form label-position="top">
      <el-form-item label="工具名称 (调用标识)">
        <el-input
          v-model="form.name"
          placeholder="例如:extract_pdf"
          :disabled="isEdit && tool?.builtin"
        />
        <p class="hint">代码里 ``@tool`` 装饰器使用的函数名,创建后建议不再修改。</p>
      </el-form-item>

      <el-form-item label="显示名称">
        <el-input v-model="form.display_name" placeholder="例如:提取 PDF 文本" />
      </el-form-item>

      <el-form-item label="描述">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          placeholder="这个工具能做什么"
        />
      </el-form-item>

      <!-- ---------- 工具包(拖拽上传) ---------- -->
      <el-form-item label="工具包 (zip)">
        <el-upload
          ref="uploadRef"
          class="zip-drop"
          drag
          :auto-upload="false"
          :limit="1"
          accept=".zip"
          :disabled="isEdit && tool?.builtin"
          :on-change="onChange"
          :on-remove="onRemove"
          :file-list="fileList"
        >
          <div class="drop">
            <i class="bi bi-file-earmark-zip drop-icon"></i>
            <div v-if="!fileList.length" class="drop-text">
              把 zip 包拖到这里,或<em>点击选择文件</em>
            </div>
            <div v-else class="drop-text">
              {{ fileList[0].name }}
              <span class="drop-meta">· {{ formatBytes(fileList[0].size) }}</span>
            </div>
            <div class="drop-hint">只支持 .zip,最大 50MB</div>
          </div>
        </el-upload>

        <p class="hint">
          zip 里应含 .py 模块(调用 <code>register_tool(name, tool)</code>),
          可选 <code>manifest.json</code> 提供显示名 / 描述。
        </p>

        <details v-if="!isEdit || !tool?.builtin" class="spec">
          <summary>zip 包结构</summary>
          <pre><code>my-tool.zip
├── manifest.json      # 可选:显示名 / 描述
└── my_tool.py         # 必需:工具模块

# my_tool.py
from tools import register_tool

@tool
def greet(name: str) -&gt; str:
    """打个招呼"""
    return f"你好,{name}"

register_tool("greet", greet, display_name="打招呼")</code></pre>
        </details>
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
import { createTool, updateTool, uploadToolPackage } from '../api/tools'

const props = defineProps({
  visible: { type: Boolean, default: false },
  tool: { type: Object, default: null },
})
const emit = defineEmits(['update:visible', 'saved'])

const saving = ref(false)
const isEdit = computed(() => !!props.tool?.id)
// 内置工具只读:代码在仓库里,不允许改
const isBuiltin = computed(() => !!(props.tool?.builtin))
const form = ref(blank())
const uploadRef = ref(null)
const fileList = ref([])

function blank() {
  return { name: '', display_name: '', description: '' }
}

function formatBytes(n) {
  if (!n && n !== 0) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

watch(
  () => props.visible,
  (v) => {
    if (!v) return
    form.value = props.tool
      ? {
          name: props.tool.name,
          display_name: props.tool.display_name || '',
          description: props.tool.description || '',
        }
      : blank()
    fileList.value = []
  },
  { immediate: true },
)

function onChange(file) {
  const raw = file.raw
  if (!raw) return
  if (!raw.name.toLowerCase().endsWith('.zip')) {
    ElMessage.error('只支持上传 zip 包')
    fileList.value = []
    return
  }
  fileList.value = [file]
}

function onRemove() {
  fileList.value = []
}

async function save() {
  if (!form.value.name.trim()) {
    ElMessage.warning('工具名称不能为空')
    return
  }
  const file = fileList.value[0]?.raw || null
  saving.value = true
  try {
    if (isEdit.value) {
      const payload = {
        display_name: form.value.display_name,
        description: form.value.description,
      }
      if (!isBuiltin.value) payload.name = form.value.name
      // 带 zip → 走上传接口(替换实现),工具名不变
      if (file) {
        await uploadToolPackage(file, {
          replace_tool_id: props.tool.id,
          display_name: form.value.display_name,
          description: form.value.description,
        })
      } else {
        await updateTool(props.tool.id, payload)
      }
    } else if (file) {
      // 新建 + 带 zip → 上传 zip(工具名从 zip 里的 register_tool 取)
      await uploadToolPackage(file, {
        display_name: form.value.display_name,
        description: form.value.description,
      })
    } else {
      await createTool({ ...form.value })
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
.hint code {
  background: var(--n-bg-code);
  padding: 1px 4px;
  border-radius: var(--n-radius-sm);
  font-family: var(--n-font-mono);
}
/* 拖拽区:整块可点,虚线边框 */
.zip-drop {
  width: 100%;
}
.zip-drop :deep(.el-upload),
.zip-drop :deep(.el-upload-dragger) {
  width: 100%;
}
.zip-drop :deep(.el-upload-dragger) {
  padding: var(--n-gap-md) 0;
  background: var(--n-bg-subtle);
  border-color: var(--n-border);
  border-radius: var(--n-radius);
  transition: border-color 0.12s ease, background 0.12s ease;
}
.zip-drop :deep(.el-upload-dragger:hover) {
  border-color: var(--n-accent-border);
  background: var(--n-accent-soft);
}
.drop {
  padding: var(--n-gap-sm) 0;
  color: var(--n-text-secondary);
}
.drop-icon {
  font-size: 26px;
  color: var(--n-text-tertiary);
  margin-bottom: var(--n-gap-xs);
}
.drop-text {
  font-size: var(--n-text-sm);
}
.drop-text em {
  color: var(--n-accent);
  font-style: normal;
}
.drop-meta {
  color: var(--n-text-tertiary);
  font-size: var(--n-text-xs);
}
.drop-hint {
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  margin-top: var(--n-gap-xs);
}
/* zip 包结构说明:默认折叠 */
.spec {
  margin-top: var(--n-gap-sm);
  padding: var(--n-gap-sm) var(--n-gap-md);
  background: var(--n-bg-code);
  border-radius: var(--n-radius);
  border: 1px solid var(--n-border-light);
}
.spec summary {
  cursor: pointer;
  font-size: var(--n-text-sm);
  color: var(--n-text-secondary);
  user-select: none;
}
.spec pre {
  margin: var(--n-gap-sm) 0 0;
  overflow-x: auto;
}
.spec code {
  font-family: var(--n-font-mono);
  font-size: var(--n-text-xs);
  line-height: 1.6;
  color: var(--n-text-secondary);
}
</style>
