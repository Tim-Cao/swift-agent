<template>
  <div class="input-bar">
    <!-- 已上传 zip 提示卡 -->
    <div v-if="attachment" class="attachment-chip">
      <el-icon class="chip-icon"><Document /></el-icon>
      <span class="chip-name">{{ attachment.name }}</span>
      <span class="chip-meta">({{ formatBytes(attachment.size_bytes) }} · {{ attachment.csv_count }} CSV)</span>
      <el-button
        type="danger"
        link
        size="small"
        @click="clearAttachment"
      >移除</el-button>
    </div>

    <div class="input-row">
      <!-- el-upload 触发器:用一个 el-button 做"上传 zip"入口,
           仍支持点击选择文件(默认 slot)。el-button 比 el-icon 块更醒目,
           也更符合用户习惯。 -->
      <el-upload
        :auto-upload="true"
        :show-file-list="false"
        :http-request="customUpload"
        :before-upload="beforeUpload"
        accept=".zip"
      >
        <el-button
          :loading="uploading"
          :disabled="disabled || uploading"
          type="primary"
          plain
        >
          <el-icon class="btn-icon"><UploadFilled /></el-icon>
          <span>{{ uploading ? '上传中…' : '上传 zip' }}</span>
        </el-button>
      </el-upload>

      <el-input
        v-model="text"
        type="textarea"
        :rows="3"
        :placeholder="attachment ? '补充处理指令(基于已上传的 zip)…' : '输入消息,Enter 发送,Shift+Enter 换行'"
        :disabled="disabled || uploading"
        @keydown.enter.exact.prevent="submit"
      />
      <!-- 联网搜索开关:按钮组形式,选中态 = primary;由 WebSearchGateMiddleware
           按 enable_web_search 决定是否把 MCP 工具暴露给 LLM。 -->
      <el-button-group class="search-toggle">
        <el-button
          :type="webSearchEnabled ? 'primary' : 'default'"
          :disabled="disabled || uploading"
          @click="webSearchEnabled = true"
          title="允许主智能体通过 MCP 调用联网搜索工具"
        >
          <el-icon class="btn-icon"><Connection /></el-icon>
          <span>联网</span>
        </el-button>
        <el-button
          :type="!webSearchEnabled ? 'primary' : 'default'"
          :disabled="disabled || uploading"
          @click="webSearchEnabled = false"
          title="关闭联网搜索,仅基于已有知识回答"
        >
          <el-icon class="btn-icon"><Document /></el-icon>
          <span>本地</span>
        </el-button>
      </el-button-group>
      <el-button
        type="primary"
        :loading="disabled || uploading"
        :disabled="!text.trim() || disabled || uploading"
        @click="submit"
      >
        {{ disabled ? '生成中…' : '发送' }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, UploadFilled, Connection } from '@element-plus/icons-vue'
import { uploadZip } from '../api/uploads'

const props = defineProps({
  disabled: { type: Boolean, default: false },
  sessionId: { type: String, default: null },
})
const emit = defineEmits(['send', 'attachment-cleared'])

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
 */
const attachment = ref(null)

function formatBytes(n) {
  if (!n && n !== 0) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

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

function clearAttachment() {
  attachment.value = null
  emit('attachment-cleared')
}

function submit() {
  const t = text.value.trim()
  if (!t || props.disabled || uploading.value) return
  emit('send', {
    message: t,
    upload_dir: attachment.value?.upload_dir || null,
    enable_web_search: webSearchEnabled.value,
  })
  // 发送后清空输入与附件(开关状态保留,符合用户预期:选择一次后持续生效)
  text.value = ''
  attachment.value = null
}

defineExpose({ clearAttachment })
</script>

<style scoped>
.input-bar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #eee;
  background: #fff;
}
.input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.zip-uploader {
  flex: 0 0 auto;
}
.btn-icon {
  margin-right: 4px;
  font-size: 14px;
}
.search-toggle {
  flex: 0 0 auto;
  align-self: flex-end;
}
.attachment-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
  border-radius: 4px;
  color: #303133;
  font-size: 13px;
  align-self: flex-start;
}
.chip-icon { color: #409eff; }
.chip-name { font-weight: 500; }
.chip-meta { color: #909399; font-size: 12px; }
</style>