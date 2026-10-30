<template>
  <div class="knowledge-view">
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card class="panel-card">
          <template #header>
            <div class="card-header">
              <span>文档上传</span>
              <el-button type="primary" @click="refreshDocs" size="small">刷新</el-button>
            </div>
          </template>

          <el-upload
            ref="uploadRef"
            class="upload-area"
            drag
            multiple
            :auto-upload="true"
            :show-file-list="false"
            :http-request="handleUpload"
            :on-success="onUploadSuccess"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="upload-text">拖拽文件到此处或<em>点击上传</em></div>
            <template #tip>
              <div class="upload-tip">支持 .txt, .md, .pdf, .docx, .json, .yaml, .csv</div>
            </template>
          </el-upload>

          <el-divider />

          <div class="docs-list">
            <h4>已上传文档 ({{ documentCount }})</h4>
            <el-table :data="documents" size="small" style="width: 100%">
              <el-table-column prop="name" label="文件名" min-width="150" />
              <el-table-column label="大小" width="100">
                <template #default="{ row }">
                  {{ formatSize(row.size) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button
                    type="danger"
                    size="small"
                    text
                    @click="deleteDoc(row.name)"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="panel-card">
          <template #header>
            <div class="card-header">
              <span>索引构建</span>
            </div>
          </template>

          <el-descriptions :column="1" border>
            <el-descriptions-item label="集合名称">
              <el-input v-model="collectionName" size="small" style="width: 200px" />
            </el-descriptions-item>
            <el-descriptions-item label="文档路径">
              <el-input :model-value="docsPath" disabled size="small" />
            </el-descriptions-item>
            <el-descriptions-item label="索引状态">
              <el-tag :type="status.ready ? 'success' : 'warning'" size="small">
                {{ status.ready ? '已就绪' : '未就绪' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="文档数量">
              {{ documentCount }} 个
            </el-descriptions-item>
          </el-descriptions>

          <el-divider />

          <div class="build-section">
            <el-button
              type="primary"
              @click="buildIndex"
              :loading="building"
              :disabled="documentCount === 0"
            >
              构建索引
            </el-button>
            <el-button @click="refreshStatus" size="small">刷新状态</el-button>
          </div>

          <div v-if="buildMessage" class="build-message">
            <el-alert :title="buildMessage" :type="buildSuccess ? 'success' : 'error'" show-icon />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

const collectionName = ref('opsweave')
const docsPath = ref('./data/documents')
const documents = ref([])
const documentCount = ref(0)
const building = ref(false)
const buildMessage = ref('')
const buildSuccess = ref(false)

const status = reactive({
  ready: false,
  collection: '',
  build_status: 'idle',
})

onMounted(() => {
  refreshDocs()
  refreshStatus()
})

async function refreshDocs() {
  try {
    const { data } = await axios.get('/api/knowledge/documents')
    documents.value = data.documents
    documentCount.value = data.count
  } catch (e) {
    console.error('Failed to load documents:', e)
  }
}

async function refreshStatus() {
  try {
    const { data } = await axios.get('/api/knowledge/status')
    status.ready = data.ready
    status.collection = data.collection
    status.build_status = data.build_status
  } catch (e) {
    console.error('Failed to load status:', e)
  }
}

async function handleUpload(options) {
  const formData = new FormData()
  formData.append('file', options.file)

  try {
    const { data } = await axios.post('/api/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success(data.message || '上传成功')
    refreshDocs()
  } catch (e) {
    ElMessage.error('上传失败: ' + (e.response?.data?.detail || e.message))
  }
}

function onUploadSuccess() {
  // Already handled in handleUpload
}

async function deleteDoc(name) {
  try {
    await ElMessageBox.confirm(`确定删除 ${name} ?`, '提示', {
      type: 'warning',
    })
    const { data } = await axios.delete(`/api/knowledge/documents/${name}`)
    ElMessage.success(data.message || '删除成功')
    refreshDocs()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

async function buildIndex() {
  building.value = true
  buildMessage.value = ''
  try {
    const { data } = await axios.post('/api/knowledge/build', {
      collection_name: collectionName.value,
    })
    if (data.status === 'built') {
      buildSuccess.value = true
      buildMessage.value = data.message || '索引构建完成'
      ElMessage.success(buildMessage.value)
      refreshStatus()
    } else {
      buildSuccess.value = false
      buildMessage.value = '构建失败'
      ElMessage.error(buildMessage.value)
    }
  } catch (e) {
    buildSuccess.value = false
    buildMessage.value = e.response?.data?.detail || e.message || '构建失败'
    ElMessage.error(buildMessage.value)
  } finally {
    building.value = false
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.knowledge-view {
  height: 100%;
}

.panel-card {
  height: 100%;
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.upload-area {
  width: 100%;
}

.upload-icon {
  font-size: 48px;
  color: #4fc3f7;
}

.upload-text {
  margin-top: 16px;
  color: #999;
}

.upload-text em {
  color: #4fc3f7;
}

.upload-tip {
  margin-top: 8px;
  font-size: 12px;
  color: #aaa;
}

.docs-list h4 {
  margin-bottom: 12px;
}

.build-section {
  display: flex;
  gap: 12px;
}

.build-message {
  margin-top: 16px;
}
</style>
