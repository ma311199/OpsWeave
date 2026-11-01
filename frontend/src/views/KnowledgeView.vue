<template>
  <div class="knowledge-view">
    <el-card class="panel-card">
      <template #header>
        <div class="card-header"><span>{{ isAdmin ? '知识库管理与审批' : '我的知识库' }}</span><el-button size="small" @click="refresh">刷新</el-button></div>
      </template>
      <div class="upload-row">
        <el-upload :show-file-list="false" :http-request="handleUpload" accept=".txt,.md,.pdf,.docx,.json,.yaml,.yml,.csv">
          <el-button type="primary" :loading="uploading">上传文档</el-button>
        </el-upload>
        <el-select v-model="selectedCollection" placeholder="选择知识库" style="width:300px" :loading="collectionsLoading" :disabled="collections.length === 0"><el-option v-for="item in collections" :key="item.name" :label="item.name" :value="item.name"><div class="collection-option"><span>{{ item.name }}</span><small>{{ item.description || '无描述' }} · {{ item.row_count }} 条数据</small></div></el-option></el-select>
        <el-button size="small" :loading="collectionsLoading" @click="loadCollections">刷新知识库</el-button>
        <span v-if="!collectionsLoading && collections.length === 0" class="hint">管理员配置的知识库为空，或当前配置的 Milvus 中没有对应知识库</span>
        <span class="hint">当前选择：{{ selectedCollection || '未选择' }}。块大小与重叠按 Token 计；Embedding 上限 {{ embeddingMaxTokens }} tokens。超过上限将报错，不会自动拆分。</span>
      </div>
      <div v-if="isAdmin" class="filters-row">
        <el-input v-model="filters.owner" clearable placeholder="按用户筛选" style="width:180px" />
        <el-select v-model="filters.collection" clearable placeholder="全部知识库" style="width:180px"><el-option v-for="item in collections" :key="item.name" :label="item.name" :value="item.name" /></el-select>
        <el-select v-model="filters.status" clearable placeholder="全部状态" style="width:160px"><el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
      </div>
      <el-table :data="filteredDocuments" row-key="id" style="width:100%">
        <el-table-column prop="filename" label="文件名" min-width="180" />
        <el-table-column v-if="isAdmin" prop="owner" label="上传用户" width="120" />
        <el-table-column prop="collection_name" label="知识库" width="160" />
        <el-table-column label="大小" width="100"><template #default="{ row }">{{ formatSize(row.size) }}</template></el-table-column>
        <el-table-column label="文档切分" width="180"><template #default="{ row }">
          <el-button v-if="!isAdmin && ['uploaded','rejected','failed'].includes(row.status)" link type="primary" @click="openChunkConfig(row)">配置切分策略</el-button>
          <span v-else-if="row.status !== 'uploaded'">{{ strategyName(row.strategy) }} · {{ row.strategy === 'semantic' ? `预切分上限 ${row.semantic_max_chunk_size}` : `${row.chunk_size} / ${row.chunk_overlap} tokens` }}</span>
          <span v-else>—</span>
        </template></el-table-column>
        <el-table-column label="状态" width="120"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusName(row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="error" label="错误信息" min-width="150" show-overflow-tooltip />
        <el-table-column label="操作" min-width="190" fixed="right"><template #default="{ row }">
          <el-button v-if="['uploaded','rejected','failed'].includes(row.status)" link type="primary" :loading="row.actionLoading" :disabled="row.actionLoading" @click="apply(row)">{{ row.actionLoading ? '正在提交' : isAdmin ? '开始构建' : '申请构建' }}</el-button>
          <el-button v-if="isAdmin && row.status === 'pending'" link type="success" :loading="row.actionLoading" @click="review(row, true)">批准并构建</el-button>
          <el-button v-if="isAdmin && row.status === 'pending'" link type="danger" :disabled="row.actionLoading" @click="review(row, false)">拒绝</el-button>
          <el-tag v-if="row.status === 'processing'" type="warning">正在构建</el-tag>
          <el-button v-if="!isAdmin && row.status === 'pending'" link type="warning" @click="cancelApplication(row)">撤销构建</el-button>
          <el-button v-if="row.status === 'completed'" link type="primary" @click="showChunks(row)">查看文档块</el-button>
          <el-button v-if="row.status !== 'pending' && row.status !== 'processing'" link type="danger" @click="remove(row)">删除</el-button>
        </template></el-table-column>
      </el-table>
      <el-empty v-if="documents.length === 0" description="暂无文档" />
    </el-card>

    <el-dialog v-model="chunkConfigVisible" :title="`文档切分配置 - ${configDocument?.filename || ''}`" width="min(560px, 94vw)">
      <el-form v-if="configDocument" label-width="130px">
        <el-form-item label="切分策略">
          <el-select v-model="configDocument.selectedStrategy" @change="changeStrategy(configDocument)">
            <el-option v-for="item in strategies" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="configDocument.selectedStrategy !== 'semantic'" label="块大小 (tokens)">
          <el-input-number v-model="configDocument.selectedChunkSize" :min="1" :max="embeddingMaxTokens" controls-position="right" />
        </el-form-item>
        <el-form-item v-if="configDocument.selectedStrategy === 'structure'" label="文档格式">
          <el-select v-model="configDocument.structureFormat">
            <el-option label="Markdown" value="markdown" />
            <el-option label="HTML" value="html" />
            <el-option label="LaTeX" value="latex" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="configDocument.selectedStrategy === 'semantic'" label="语义边界阈值">
          <el-slider v-model="configDocument.semanticThreshold" :min="50" :max="99" show-input />
        </el-form-item>
        <el-form-item v-if="configDocument.selectedStrategy === 'summary'" label="摘要模型">
          <span>使用系统当前配置的大语言模型</span>
        </el-form-item>
        <el-form-item v-if="!['fixed', 'token', 'semantic'].includes(configDocument.selectedStrategy)" label="前后重叠 (tokens)">
          <el-input-number v-model="configDocument.selectedOverlap" :min="0" :max="Math.min(configDocument.selectedChunkSize - 1, embeddingMaxTokens - 1)" controls-position="right" />
        </el-form-item>
        <el-form-item v-if="configDocument.selectedStrategy === 'semantic'" label="语义预切分上限">
          <el-input-number v-model="configDocument.semanticMaxChunkSize" :min="1" :max="embeddingMaxTokens" controls-position="right" />
        </el-form-item>
        <div class="hint">Embedding 最大输入限制：{{ embeddingMaxTokens }} tokens。超过限制会在构建时终止并显示错误，不会自动再次切分。</div>
      </el-form>
      <template #footer>
        <el-button @click="chunkConfigVisible = false">关闭</el-button>
        <el-button type="primary" @click="saveChunkConfig">保存配置</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="chunksVisible" :title="`文档块 - ${selectedDocument?.filename || ''}`" width="min(1000px, 94vw)">
      <el-table :data="chunks" height="60vh" style="width:100%">
        <el-table-column prop="ordinal" label="#" width="70" />
        <el-table-column prop="text" label="原始文本块" min-width="350" show-overflow-tooltip />
        <el-table-column v-if="selectedDocument?.strategy === 'summary'" prop="embedding_text" label="用于向量化的摘要" min-width="300" show-overflow-tooltip />
        <el-table-column prop="user_id" label="用户 ID" width="130" />
        <el-table-column prop="document_id" label="文档 ID" width="220" />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'

const documents = ref([])
const strategies = ref([])
const collections = ref([])
const collectionsLoading = ref(false)
const selectedCollection = ref('')
const isAdmin = ref(false)
const uploading = ref(false)
const chunkConfigVisible = ref(false)
const configDocument = ref(null)
const chunksVisible = ref(false)
const chunks = ref([])
const selectedDocument = ref(null)
const embeddingMaxTokens = ref(8192)
const filters = reactive({ owner: '', collection: '', status: '' })
const statusOptions = [
  { value: 'uploaded', label: '待申请' }, { value: 'pending', label: '待审批' },
  { value: 'processing', label: '正在构建' }, { value: 'completed', label: '已完成' },
  { value: 'rejected', label: '已拒绝' }, { value: 'failed', label: '处理失败' },
]
const filteredDocuments = computed(() => documents.value.filter(row =>
  (!filters.owner || row.owner.toLowerCase().includes(filters.owner.trim().toLowerCase())) &&
  (!filters.collection || row.collection_name === filters.collection) &&
  (!filters.status || row.status === filters.status),
))
let statusPoll

onMounted(async () => { 
  try {
    const { data } = await axios.get('/api/auth/me')
    isAdmin.value = data.role === 'admin'
    const strategyData = (await axios.get('/api/knowledge/strategies')).data
    strategies.value = strategyData.strategies
    embeddingMaxTokens.value = strategyData.embedding_max_tokens
    await loadCollections()
    await refresh()
    statusPoll = window.setInterval(async () => {
      if (documents.value.some(row => row.status === 'processing')) await refresh()
    }, 3000)
  } catch (error) { ElMessage.error(error.response?.data?.detail || '加载知识库失败') }
})
onUnmounted(() => window.clearInterval(statusPoll))

async function loadCollections() {
  collectionsLoading.value = true
  try {
    const { data } = await axios.get('/api/knowledge/collections')
    collections.value = data.collections
    if (!collections.value.some(item => item.name === selectedCollection.value)) selectedCollection.value = collections.value[0]?.name || ''
  } catch (error) { ElMessage.error(error.response?.data?.detail || '加载知识库失败') }
  finally { collectionsLoading.value = false }
}
async function refresh() {
  documents.value = (await axios.get('/api/knowledge/documents')).data.documents.map(row => ({ ...row, selectedStrategy: row.strategy === 'token' || !row.strategy ? 'fixed' : row.strategy, selectedChunkSize: row.chunk_size || 512, selectedOverlap: row.chunk_overlap || 64, semanticMaxChunkSize: row.semantic_max_chunk_size || 2048, structureFormat: row.structure_format || 'markdown', semanticThreshold: row.semantic_threshold || 95 }))
}
async function handleUpload(options) {
  uploading.value = true
  try {
    if (!selectedCollection.value) { ElMessage.error('请先选择知识库'); return }
    const form = new FormData(); form.append('file', options.file)
    await axios.post(`/api/knowledge/upload?collection_name=${encodeURIComponent(selectedCollection.value)}`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
    ElMessage.success(`已上传到知识库 ${selectedCollection.value}，请选择切分策略并申请构建`)
    await refresh()
  } catch (error) { ElMessage.error(error.response?.data?.detail || '上传失败') }
  finally { uploading.value = false }
}
function openChunkConfig(row) {
  configDocument.value = row
  chunkConfigVisible.value = true
}
function saveChunkConfig() {
  const row = configDocument.value
  if (!row) return
  if (!['fixed', 'token', 'semantic'].includes(row.selectedStrategy) && row.selectedOverlap >= row.selectedChunkSize) { ElMessage.error('重叠 Token 数必须小于块大小'); return }
  if ((row.selectedStrategy !== 'semantic' && row.selectedChunkSize > embeddingMaxTokens.value) || (row.selectedStrategy === 'semantic' && row.semanticMaxChunkSize > embeddingMaxTokens.value)) {
    ElMessage.error(`块大小不能超过 Embedding 最大限制 ${embeddingMaxTokens.value} tokens`)
    return
  }
  chunkConfigVisible.value = false
  ElMessage.success('切分配置已保存')
}
async function apply(row) {
  try {
    const overlap = ['fixed', 'token', 'semantic'].includes(row.selectedStrategy) ? 0 : row.selectedOverlap
    if (overlap >= row.selectedChunkSize) { ElMessage.error('重叠 Token 数必须小于块大小'); return }
    if (row.selectedChunkSize > embeddingMaxTokens.value || (row.selectedStrategy === 'semantic' && row.semanticMaxChunkSize > embeddingMaxTokens.value)) { ElMessage.error(`块大小不能超过 Embedding 最大限制 ${embeddingMaxTokens.value} tokens`); return }
    row.actionLoading = true
    const { data } = await axios.post(`/api/knowledge/documents/${row.id}/apply`, { strategy: row.selectedStrategy, chunk_size: row.selectedChunkSize, overlap, semantic_max_chunk_size: row.semanticMaxChunkSize, structure_format: row.structureFormat, semantic_threshold: row.semanticThreshold, collection_name: row.collection_name || selectedCollection.value })
    ElMessage.success(data.status === 'completed' ? '文档索引构建完成' : data.status === 'processing' ? '已开始构建，正在后台处理' : '申请已提交，等待管理员审批'); await refresh()
  } catch (error) { ElMessage.error(error.response?.data?.detail || '提交失败') }
  finally { row.actionLoading = false }
}
async function review(row, approve) {
  try {
    row.actionLoading = true
    const { data } = await axios.post(`/api/knowledge/applications/${row.id}/review`, { approve })
    ElMessage.success(approve ? '已批准，文档正在后台构建' : '申请已拒绝'); await refresh()
  } catch (error) { ElMessage.error(error.response?.data?.detail || '审批/构建失败'); await refresh() }
  finally { row.actionLoading = false }
}
async function cancelApplication(row) {
  try {
    await ElMessageBox.confirm(`撤销“${row.filename}”的构建申请？`, '撤销申请', { type: 'warning' })
    await axios.post(`/api/knowledge/documents/${row.id}/cancel-application`)
    ElMessage.success('申请已撤销')
    await refresh()
  } catch (error) { if (error !== 'cancel') ElMessage.error(error.response?.data?.detail || '撤销申请失败') }
}
async function showChunks(row) {
  selectedDocument.value = row
  chunks.value = (await axios.get(`/api/knowledge/documents/${row.id}/chunks`)).data.chunks
  chunksVisible.value = true
}
async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除“${row.filename}”吗？`, '确认删除', { type: 'warning' })
    await axios.delete(`/api/knowledge/documents/${row.id}`); ElMessage.success('文档已删除'); await refresh()
  } catch (error) { if (error !== 'cancel') ElMessage.error(error.response?.data?.detail || '删除失败') }
}
function changeStrategy(row) { if (row.selectedStrategy === 'semantic' && row.semanticMaxChunkSize > embeddingMaxTokens.value) row.semanticMaxChunkSize = embeddingMaxTokens.value }
function strategyName(id) { if (id === 'token') id = 'fixed'; return strategies.value.find(item => item.id === id)?.name || id }
function statusName(value) { return ({ uploaded: '待申请', pending: '待审批', processing: '处理中', completed: '已完成', rejected: '已拒绝', failed: '处理失败' })[value] || value }
function statusType(value) { return ({ completed: 'success', pending: 'warning', processing: 'warning', rejected: 'danger', failed: 'danger' })[value] || 'info' }
function formatSize(bytes) { if (bytes < 1024) return `${bytes} B`; if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`; return `${(bytes / (1024 * 1024)).toFixed(1)} MB` }
</script>

<style scoped>
.knowledge-view { height: 100%; }
.panel-card { margin-bottom: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.upload-row { display: flex; align-items: center; gap: 16px; margin-bottom: 18px; }
.hint { color: #777; font-size: 13px; }
.collection-option { display: flex; justify-content: space-between; gap: 18px; }
.collection-option small { color: #8b8f97; }
@media (max-width: 680px) { .upload-row { align-items: flex-start; flex-direction: column; } }
</style>
