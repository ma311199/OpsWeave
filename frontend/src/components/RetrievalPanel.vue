<template>
  <el-card shadow="never" class="retrieval-card">
    <template #header>
      <div class="retrieval-header">
        <span class="retrieval-title">知识库检索</span>
        <el-button
          size="small"
          type="primary"
          :loading="loading"
          @click="search"
        >
          检索
        </el-button>
      </div>
    </template>

    <el-input
      v-model="query"
      type="textarea"
      :rows="4"
      placeholder="输入检索关键词，Ctrl+Enter 发送..."
      @keydown.ctrl.enter="search"
    />

    <div v-if="results.length > 0" class="retrieval-results">
      <el-divider />
      <div v-for="(r, i) in results" :key="i" class="result-item">
        <div class="result-meta">
          <el-tag size="small" type="success">相似度: {{ r.score.toFixed(4) }}</el-tag>
          <span class="result-source">{{ r.source }}</span>
        </div>
        <div class="result-text">{{ r.text }}</div>
      </div>
    </div>

    <div v-else-if="!loading" class="empty-state">
      <el-empty description="暂无检索结果" />
    </div>
  </el-card>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'

const props = defineProps({
  role: { type: String, default: 'admin' },
})

const query = ref('')
const results = ref([])
const loading = ref(false)

async function search() {
  const q = query.value.trim()
  if (!q) {
    ElMessage.warning('请输入检索关键词')
    return
  }

  loading.value = true
  try {
    const resp = await axios.post('/api/retrieval/search', {
      query: q,
      top_k: 5,
      role: props.role,
    })
    results.value = resp.data.results
  } catch (err) {
    results.value = []
    ElMessage.error(err.response?.data?.detail || '检索失败，请检查后端服务')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.retrieval-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.retrieval-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.retrieval-title {
  font-weight: 600;
  font-size: 15px;
}

.retrieval-results {
  flex: 1;
  overflow-y: auto;
  margin-top: 12px;
}

.result-item {
  padding: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.result-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.result-source {
  font-size: 12px;
  color: #909399;
}

.result-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
}

.empty-state {
  margin-top: 40px;
}
</style>
