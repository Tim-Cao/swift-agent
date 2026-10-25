<template>
  <div class="composer">
    <!--
      整个输入区是一个盒子:上边框包住 textarea,下边框包住一排图标按钮,
      两部分共用一条外边框(中间不断开)。图标行在底部靠右。
    -->
    <div class="composer-box" :class="{ 'composer-box-disabled': disabled }">
      <el-input
        v-model="text"
        type="textarea"
        :rows="3"
        class="composer-input"
        :placeholder="placeholder"
        :disabled="disabled || uploading"
        @keydown.enter.exact.prevent="submit"
      />

      <div class="composer-bar">
        <div class="bar-left">
          <!-- 上传 zip:el-upload 的触发器 -->
          <el-upload
            :auto-upload="true"
            :show-file-list="false"
            :http-request="customUpload"
            :before-upload="beforeUpload"
            accept=".zip"
          >
            <IconButton
              icon="bi-paperclip"
              title="上传 zip 包"
              :loading="uploading"
              :disabled="disabled || uploading"
            />
          </el-upload>

          <!-- 联网搜索开关:两个图标按钮,选中态=primary -->
          <IconButton
            icon="bi-globe"
            :variant="webSearchEnabled ? 'primary' : 'ghost'"
            title="允许联网搜索"
            :disabled="disabled || uploading"
            @click="webSearchEnabled = true"
          />
          <IconButton
            icon="bi-hdd"
            :variant="!webSearchEnabled ? 'primary' : 'ghost'"
            title="仅基于已有知识回答"
            :disabled="disabled || uploading"
            @click="webSearchEnabled = false"
          />
        </div>

        <div class="bar-right">
          <span v-if="uploadedName" class="uploaded-hint">
            <i class="bi bi-file-earmark-zip"></i>
            {{ uploadedName }}
          </span>
          <IconButton
            icon="bi-arrow-up"
            variant="primary"
            title="发送(Enter)"
            :disabled="!text.trim() || disabled || uploading"
            @click="submit"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import IconButton from './IconButton.vue'
import { uploadZip } from '../api/uploads'

const props = defineProps({
  disabled: { type: Boolean, default: false },
  sessionId: { type: String, default: null },
})
const emit = defineEmits(['send'])

const text = ref('')
const uploading = ref(false)
// 联网搜索开关:默认关闭。emit 给父组件时一并带上,由后端 WebSearchGateMiddleware
// 按本轮 enable_web_search 决定是否把 MCP 工具暴露给 LLM。
const webSearchEnabled = ref(false)
/**
 * attachment: {
 *   name: string,            // 原始文件名
 *   session_id: string,
 *   upload_dir: string,      // 后端返回的目录(/tmp/swift-agent/<sid>/...)
 *   csv_files: string[],
 *   zip_path: string,
 *   size_bytes: number,
 * }
 * 上传后随消息一起发给后端,后端写进 user 消息的 meta —— 前端在**气泡里**
 * 渲染文件卡,刷新页面也不会丢。
 */
const attachment = ref(null)

const uploadedName = computed(() => attachment.value?.name || '')

const placeholder = computed(() =>
  attachment.value
    ? '补充处理指令(基于已上传的 zip)…'
    : '输入消息,Enter 发送,Shift+Enter 换行',
)

function beforeUpload(file) {
  // 限制 100MB(后端也会再校验)
  const max = 100 * 1024 * 1024
  if (file.size > max) {
    ElMessage.error('zip 文件不能超过 100MB')
    return false
  }
  if (!file.name.toLowerCase().endsWith('.zip')) {
    ElMessage.error('只支持 .zip 压缩包')
    return false
  }
  return true
}

async function customUpload(option) {
  uploading.value = true
  try {
    const res = await uploadZip(option.file, props.sessionId || undefined)
    attachment.value = {
      name: option.file.name,
      session_id: res.session_id,
      upload_dir: res.upload_dir,
      csv_files: res.csv_files || [],
      zip_path: res.zip_path,
      size_bytes: res.size_bytes,
      csv_count: (res.csv_files || []).length,
    }
    ElMessage.success(`已上传,共 ${attachment.value.csv_count} 个 CSV`)
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '上传失败'
    ElMessage.error(`上传失败:${msg}`)
  } finally {
    uploading.value = false
  }
}

function submit() {
  const t = text.value.trim()
  if (!t || props.disabled || uploading.value) return
  emit('send', {
    message: t,
    upload_dir: attachment.value?.upload_dir || null,
    // 附件描述随消息一起发,后端落进 user 消息的 meta.attachments
    attachment: attachment.value
      ? {
          name: attachment.value.name,
          size_bytes: attachment.value.size_bytes,
          csv_count: attachment.value.csv_count,
        }
      : null,
    enable_web_search: webSearchEnabled.value,
  })
  // 发送后清空输入(联网开关保留,符合用户预期:选择一次后持续生效)
  text.value = ''
  attachment.value = null
}

</script>

<style scoped>
.composer {
  padding: var(--n-gap) var(--n-gap-xl) var(--n-gap-md);
  border-top: 1px solid var(--n-border-light);
  background: var(--n-bg);
}

/* 输入区外框:上下两块共用这一条边框 */
.composer-box {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--n-border);
  border-radius: var(--n-radius-lg);
  background: var(--n-bg-card);
  transition: border-color 0.12s ease;
}
.composer-box:focus-within {
  border-color: var(--n-accent-border);
}
.composer-box-disabled {
  opacity: 0.6;
}

.composer-input :deep(.el-textarea__inner) {
  border: none;
  border-radius: var(--n-radius-lg) var(--n-radius-lg) 0 0;
  box-shadow: none;
  background: transparent;
  padding: var(--n-gap) var(--n-gap) var(--n-gap-xs);
  font-size: var(--n-text-md);
  line-height: 1.6;
  resize: none;
  min-height: 62px;
}
.composer-input :deep(.el-textarea__inner:focus) {
  box-shadow: none;
}

/* 底部图标行:跟输入框共用外框,所以自己不画边框,只跟上方留一条分隔 */
.composer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--n-gap-sm);
  padding: var(--n-gap-xs) var(--n-gap-sm) var(--n-gap-sm);
  border-top: 1px solid var(--n-border-light);
}
.bar-left,
.bar-right {
  display: flex;
  align-items: center;
  gap: var(--n-gap-xs);
}
.bar-right {
  margin-left: auto;
}
.uploaded-hint {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--n-text-xs);
  color: var(--n-text-tertiary);
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
