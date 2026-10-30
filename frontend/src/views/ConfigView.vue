<template>
  <div class="config-view">
    <el-card class="config-card">
      <template #header>
        <div class="card-header">
          <span>系统配置管理</span>
          <el-button type="primary" @click="saveConfigs" :loading="saving">保存配置</el-button>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <!-- LLM Config -->
        <el-tab-pane label="LLM 配置" name="llm">
          <el-form :model="llmConfig" label-width="120px">
            <el-form-item label="Base URL">
              <el-input v-model="llmConfig.base_url" placeholder="https://api.openai.com/v1" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="llmConfig.api_key" type="password" show-password placeholder="sk-..." />
            </el-form-item>
            <el-form-item label="模型名称">
              <el-input v-model="llmConfig.model" placeholder="gpt-4o-mini" />
            </el-form-item>
            <el-form-item label="温度">
              <el-slider v-model="llmConfig.temperature" :min="0" :max="2" :step="0.1" show-input style="width: 300px" />
            </el-form-item>
            <el-form-item>
              <el-button @click="testConnection('llm')" :loading="testing === 'llm'">测试连接</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- Embedding Config -->
        <el-tab-pane label="Embedding 配置" name="embedding">
          <el-form :model="embeddingConfig" label-width="120px">
            <el-form-item label="Base URL">
              <el-input v-model="embeddingConfig.base_url" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="embeddingConfig.api_key" type="password" show-password placeholder="sk-..." />
            </el-form-item>
            <el-form-item label="模型名称">
              <el-input v-model="embeddingConfig.model" placeholder="qwen3-vl-embedding" />
            </el-form-item>
            <el-form-item label="向量维度">
              <el-input-number v-model="embeddingConfig.dimension" :min="1" :max="4096" :step="1" />
            </el-form-item>
            <el-form-item>
              <el-button @click="testConnection('embedding')" :loading="testing === 'embedding'">测试连接</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- Milvus Config -->
        <el-tab-pane label="Milvus 配置" name="milvus">
          <!-- Connection Settings -->
          <el-form :model="milvusConfig" label-width="120px">
            <el-form-item label="URI">
              <el-input v-model="milvusConfig.uri" placeholder="http://localhost:19530" />
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="milvusConfig.user" placeholder="mm" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="milvusConfig.password" type="password" show-password placeholder="..." />
            </el-form-item>
            <el-form-item label="数据库名">
              <el-input v-model="milvusConfig.database" placeholder="opsweave" />
            </el-form-item>
            <el-form-item>
              <el-button @click="testConnection('milvus')" :loading="testing === 'milvus'">测试连接</el-button>
            </el-form-item>
          </el-form>

          <el-divider />

          <!-- Collections Management -->
          <div class="collections-section">
            <div class="section-header">
              <h3>数据库集合 ({{ remoteCollections.length }})</h3>
              <div>
                <el-button type="primary" size="small" @click="showAddDialog = true">添加集合</el-button>
                <el-button size="small" @click="loadRemoteCollections" :loading="loadingRemote">刷新</el-button>
              </div>
            </div>

            <el-table :data="remoteCollections" border size="small" style="width: 100%">
              <el-table-column prop="name" label="集合名称" min-width="120" />
              <el-table-column label="描述" min-width="150">
                <template #default="{ row }">
                  {{ row.description || '—' }}
                </template>
              </el-table-column>
              <el-table-column label="数据量" width="80">
                <template #default="{ row }">
                  {{ row.row_count || 0 }}
                </template>
              </el-table-column>
              <el-table-column label="字段" min-width="200">
                <template #default="{ row }">
                  <el-tag v-for="f in row.fields" :key="f.name" size="small" style="margin-right:4px">
                    {{ f.name }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="索引" min-width="120">
                <template #default="{ row }">
                  <el-tag v-for="idx in row.index" :key="idx.field" size="small" style="margin-right:4px" type="success">
                    {{ idx.index_type }}/{{ idx.metric_type }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" type="primary" @click="editCollection(row)">修改</el-button>
                  <el-button size="small" type="danger" @click="deleteCollection(row.name)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>

            <el-empty v-if="remoteCollections.length === 0" description="暂无集合，点击添加" />
          </div>

          <el-divider />

          <!-- Local Collections Design -->
          <div class="collections-section">
            <div class="section-header">
              <h3>本地配置的集合</h3>
            </div>
            <el-empty v-if="milvusConfig.collections.length === 0" description="暂无配置" />
            <el-card v-for="(col, index) in milvusConfig.collections" :key="index" class="collection-card">
              <template #header>
                <div class="collection-header">
                  <span class="collection-title">{{ col.name || '未命名集合' }}</span>
                  <el-button type="danger" size="small" text @click="removeCollection(index)">删除</el-button>
                </div>
              </template>
              <el-form label-width="100px" size="small">
                <el-form-item label="集合名称">
                  <el-input v-model="col.name" placeholder="例如：ops_knowledge" />
                </el-form-item>
                <el-form-item label="描述">
                  <el-input v-model="col.description" placeholder="集合用途说明" />
                </el-form-item>
                <el-form-item label="向量维度">
                  <el-input-number v-model="col.dimension" :min="1" :max="4096" :step="1" style="width: 150px" />
                </el-form-item>
                <el-form-item label="度量类型">
                  <el-select v-model="col.metric_type" style="width: 150px">
                    <el-option label="L2 (欧氏距离)" value="L2" />
                    <el-option label="IP (内积)" value="IP" />
                    <el-option label="COSINE (余弦)" value="COSINE" />
                  </el-select>
                </el-form-item>
                <el-form-item label="索引类型">
                  <el-select v-model="col.index_type" style="width: 150px">
                    <el-option label="AUTOINDEX" value="AUTOINDEX" />
                    <el-option label="IVF_FLAT" value="IVF_FLAT" />
                    <el-option label="IVF_SQ8" value="IVF_SQ8" />
                    <el-option label="HNSW" value="HNSW" />
                    <el-option label="FLAT" value="FLAT" />
                  </el-select>
                </el-form-item>
                <el-form-item>
                  <el-button size="small" @click="createCollection(col)" :loading="creating === col.name">创建到 Milvus</el-button>
                </el-form-item>
              </el-form>
            </el-card>
          </div>
        </el-tab-pane>

        <!-- Agent Config -->
        <el-tab-pane label="Agent 配置" name="agent">
          <el-form :model="agentConfig" label-width="120px">
            <el-form-item label="最大迭代次数">
              <el-input-number v-model="agentConfig.max_iterations" :min="1" :max="50" />
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- Add/Edit Collection Dialog -->
    <el-dialog v-model="showAddDialog" :title="editingCollection ? '修改集合' : '添加集合'" width="500px">
      <el-form :model="collectionForm" label-width="100px">
        <el-form-item label="集合名称">
          <el-input v-model="collectionForm.name" placeholder="例如：ops_knowledge" :disabled="editingCollection" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="collectionForm.description" placeholder="集合用途说明" />
        </el-form-item>
        <el-form-item label="向量维度">
          <el-input-number v-model="collectionForm.dimension" :min="1" :max="4096" :step="1" style="width: 150px" />
        </el-form-item>
        <el-form-item label="度量类型">
          <el-select v-model="collectionForm.metric_type" style="width: 150px">
            <el-option label="L2 (欧氏距离)" value="L2" />
            <el-option label="IP (内积)" value="IP" />
            <el-option label="COSINE (余弦)" value="COSINE" />
          </el-select>
        </el-form-item>
        <el-form-item label="索引类型">
          <el-select v-model="collectionForm.index_type" style="width: 150px">
            <el-option label="AUTOINDEX" value="AUTOINDEX" />
            <el-option label="IVF_FLAT" value="IVF_FLAT" />
            <el-option label="IVF_SQ8" value="IVF_SQ8" />
            <el-option label="HNSW" value="HNSW" />
            <el-option label="FLAT" value="FLAT" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="saveCollection" :loading="savingCollection">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'

const activeTab = ref('llm')
const saving = ref(false)
const testing = ref('')
const creating = ref('')
const loadingRemote = ref(false)
const savingCollection = ref(false)
const showAddDialog = ref(false)
const editingCollection = ref(null)

const remoteCollections = ref([])

const collectionForm = reactive({
  name: '',
  description: '',
  dimension: 2048,
  metric_type: 'L2',
  index_type: 'AUTOINDEX',
})

const llmConfig = reactive({
  base_url: '',
  api_key: '',
  model: '',
  temperature: 0.7,
})

const embeddingConfig = reactive({
  base_url: '',
  api_key: '',
  model: '',
  dimension: 2048,
})

const milvusConfig = reactive({
  uri: '',
  user: '',
  password: '',
  database: '',
  collections: [],
})

const agentConfig = reactive({
  max_iterations: 8,
})

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/config/')
    if (data.llm) {
      Object.assign(llmConfig, data.llm)
    }
    if (data.embedding) {
      Object.assign(embeddingConfig, data.embedding)
    }
    if (data.milvus) {
      Object.assign(milvusConfig, data.milvus)
      if (!milvusConfig.collections) {
        milvusConfig.collections = []
      }
    }
    if (data.agent) {
      Object.assign(agentConfig, data.agent)
    }
  } catch (e) {
    ElMessage.error('加载配置失败')
  }
})

async function saveConfigs() {
  saving.value = true
  try {
    const { data } = await axios.put('/api/config/', {
      ...llmConfig,
      ...embeddingConfig,
      ...milvusConfig,
      ...agentConfig,
    })
    ElMessage.success(data.message || '配置已保存')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function testConnection(service) {
  testing.value = service
  try {
    const { data } = await axios.post(`/api/config/test/${service}`)
    if (data.status === 'ok') {
      ElMessage.success(data.message)
      if (service === 'milvus' && data.collections) {
        remoteCollections.value = data.collections.map(name => ({ name, row_count: 0, fields: [], index: [] }))
        await loadRemoteCollections()
      }
    } else {
      ElMessage.error(data.message)
    }
  } catch (e) {
    ElMessage.error('测试失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    testing.value = ''
  }
}

async function loadRemoteCollections() {
  loadingRemote.value = true
  try {
    const { data } = await axios.get('/api/config/milvus/collections')
    if (data.status === 'ok') {
      remoteCollections.value = data.collections
    } else {
      ElMessage.error(data.message)
    }
  } catch (e) {
    ElMessage.error('获取集合列表失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loadingRemote.value = false
  }
}

function addCollection() {
  milvusConfig.collections.push({
    name: '',
    description: '',
    dimension: embeddingConfig.dimension,
    metric_type: 'L2',
    index_type: 'AUTOINDEX',
  })
}

function removeCollection(index) {
  milvusConfig.collections.splice(index, 1)
}

async function createCollection(col) {
  if (!col.name) {
    ElMessage.warning('请填写集合名称')
    return
  }
  creating.value = col.name
  try {
    const { data } = await axios.post('/api/config/milvus/create-collection', {
      name: col.name,
      description: col.description || '',
      dimension: col.dimension,
      metric_type: col.metric_type,
      index_type: col.index_type,
    })
    if (data.status === 'ok') {
      ElMessage.success(data.message)
      await loadRemoteCollections()
    } else if (data.status === 'exists') {
      ElMessage.warning(data.message)
    } else {
      ElMessage.error(data.message)
    }
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    creating.value = ''
  }
}

function editCollection(row) {
  editingCollection.value = row
  collectionForm.name = row.name
  collectionForm.description = row.description || ''
  collectionForm.dimension = row.dimension || 2048
  collectionForm.metric_type = row.metric_type || 'L2'
  collectionForm.index_type = row.index_type || 'AUTOINDEX'
  showAddDialog.value = true
}

async function saveCollection() {
  savingCollection.value = true
  try {
    if (editingCollection.value) {
      // Update existing collection
      const { data } = await axios.put(`/api/config/milvus/collections/${editingCollection.value.name}`, {
        name: editingCollection.value.name,
        description: collectionForm.description,
        dimension: collectionForm.dimension,
        metric_type: collectionForm.metric_type,
        index_type: collectionForm.index_type,
      })
      if (data.status === 'ok') {
        ElMessage.success(data.message)
        await loadRemoteCollections()
      } else {
        ElMessage.error(data.message)
      }
    } else {
      // Create new collection
      const { data } = await axios.post('/api/config/milvus/create-collection', {
        name: collectionForm.name,
        description: collectionForm.description,
        dimension: collectionForm.dimension,
        metric_type: collectionForm.metric_type,
        index_type: collectionForm.index_type,
      })
      if (data.status === 'ok') {
        ElMessage.success(data.message)
        await loadRemoteCollections()
      } else if (data.status === 'exists') {
        ElMessage.warning(data.message)
      } else {
        ElMessage.error(data.message)
      }
    }
    showAddDialog.value = false
    editingCollection.value = null
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    savingCollection.value = false
  }
}

async function deleteCollection(name) {
  try {
    await ElMessageBox.confirm(`确认删除集合 "${name}"？此操作不可恢复。`, '确认', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    const { data } = await axios.delete(`/api/config/milvus/collections/${name}`)
    if (data.status === 'ok') {
      ElMessage.success(data.message)
      await loadRemoteCollections()
    } else {
      ElMessage.error(data.message)
    }
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}
</script>

<style scoped>
.config-view {
  height: 100%;
}

.config-card {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.collections-section {
  margin-top: 20px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
}

.collection-card {
  margin-bottom: 16px;
}

.collection-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.collection-title {
  font-weight: bold;
}
</style>
