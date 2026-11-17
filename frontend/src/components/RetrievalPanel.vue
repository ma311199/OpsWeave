<template>
  <el-card shadow="never" class="retrieval-card">
    <template #header>
      <div class="retrieval-header">
        <div class="title-group">
          <div class="header-icon"><el-icon :size="20"><Collection /></el-icon></div>
          <div class="header-texts">
            <span class="retrieval-title">知识库检索</span>
            <span class="retrieval-subtitle">语义向量检索 · 直连 LangGraph 管道</span>
          </div>
        </div>
      </div>
    </template>

    <div class="search-box">
      <el-input
        v-model="query"
        type="textarea"
        :rows="4"
        resize="none"
        placeholder="描述你要查找的运维知识，例如：数据库连接池耗尽如何排查？（Ctrl+Enter 检索）"
        @keydown.ctrl.enter="search"
      />
      <div class="search-controls">
        <div class="controls-left">
          <span class="control-label">返回条数</span>
          <el-select v-model="topK" style="width: 88px">
            <el-option v-for="n in [3, 5, 10, 20]" :key="n" :label="`${n} 条`" :value="n" />
          </el-select>
        </div>
        <el-button type="primary" :loading="loading" :icon="Search" class="search-btn" @click="search">
          {{ loading ? '检索中' : '开始检索' }}
        </el-button>
      </div>
    </div>

    <div class="results-area">
      <template v-if="results.length > 0">
        <div class="results-summary">
          <el-icon><DataAnalysis /></el-icon>
          <span>共 <b>{{ results.length }}</b> 条结果，按相似度排序</span>
        </div>
        <div v-for="(r, i) in results" :key="i" class="result-item">
          <div class="result-rank">{{ i + 1 }}</div>
          <div class="result-body">
            <div class="result-meta">
              <el-tag :type="scoreType(r.score)" size="small" effect="light" round class="score-tag">
                相似度 {{ (r.score * 100).toFixed(1) }}%
              </el-tag>
              <span class="result-source">
                <el-icon><Document /></el-icon>
                {{ r.source }}
              </span>
              <el-button link size="small" class="copy-btn" @click="copyText(r.text)">
                <el-icon style="margin-right: 3px"><CopyDocument /></el-icon>复制
              </el-button>
            </div>
            <div class="result-text">{{ r.text }}</div>
          </div>
        </div>
      </template>

      <div v-else-if="loading" class="skeleton-area">
        <el-skeleton v-for="i in 3" :key="i" :rows="3" animated class="skeleton-item" />
      </div>

      <div v-else class="empty-state">
        <el-empty :image-size="90" description="输入问题，开始语义检索" />
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { Collection, Search, Document, CopyDocument, DataAnalysis } from '@element-plus/icons-vue'

const query = ref('')
const results = ref([])
const loading = ref(false)
const topK = ref(5)

function scoreType(score) {
  if (score >= 0.75) return 'success'
  if (score >= 0.5) return 'warning'
  return 'info'
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

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
      top_k: topK.value,
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
  border-radius: 12px;
  border: 1px solid #e8ecf1;
  box-shadow: 0 2px 12px rgba(16, 24, 40, 0.04);
  overflow: hidden;
}

.retrieval-card :deep(.el-card__header) {
  padding: 12px 20px;
  border-bottom: 1px solid #eef1f5;
}

.retrieval-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 16px 20px;
}

.retrieval-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: linear-gradient(135deg, #4fc3f7, #2563eb);
  color: #fff;
  display: grid;
  place-items: center;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.header-texts {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}

.retrieval-title {
  font-weight: 700;
  font-size: 15px;
  color: #1f2d3d;
}

.retrieval-subtitle {
  font-size: 12px;
  color: #8a94a6;
}

.search-box :deep(.el-textarea__inner) {
  border-radius: 10px;
  background: #f7f9fc;
  border-color: #e2e8f0;
  font-size: 14px;
  padding: 12px 14px;
  transition: all 0.2s;
}

.search-box :deep(.el-textarea__inner:focus) {
  background: #fff;
  border-color: #4fc3f7;
  box-shadow: 0 0 0 3px rgba(79, 195, 247, 0.12);
}

.search-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
}

.controls-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.control-label {
  font-size: 13px;
  color: #64748b;
}

.search-btn {
  min-width: 110px;
  border-radius: 10px;
  font-weight: 600;
}

.results-area {
  flex: 1;
  overflow-y: auto;
  margin-top: 16px;
  padding-right: 4px;
}

.results-area::-webkit-scrollbar {
  width: 6px;
}

.results-area::-webkit-scrollbar-thumb {
  background: #d3dae3;
  border-radius: 3px;
}

.results-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #64748b;
  margin-bottom: 12px;
}

.results-summary b {
  color: #2563eb;
}

.result-item {
  display: flex;
  gap: 14px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #eef1f5;
  border-radius: 10px;
  margin-bottom: 12px;
  transition: all 0.2s;
}

.result-item:hover {
  box-shadow: 0 4px 16px rgba(16, 24, 40, 0.08);
  border-color: #c9dcf2;
  transform: translateY(-1px);
}

.result-rank {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  flex-shrink: 0;
  background: linear-gradient(135deg, #4fc3f7, #2563eb);
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
}

.result-body {
  flex: 1;
  min-width: 0;
}

.result-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.score-tag {
  font-weight: 600;
  flex-shrink: 0;
}

.result-source {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #8a94a6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.copy-btn {
  margin-left: auto;
  color: #8a94a6;
  flex-shrink: 0;
}

.copy-btn:hover {
  color: #2563eb;
}

.result-text {
  font-size: 13px;
  color: #475569;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 160px;
  overflow-y: auto;
  background: #f8fafc;
  border-radius: 8px;
  padding: 10px 12px;
}

.result-text::-webkit-scrollbar {
  width: 5px;
}

.result-text::-webkit-scrollbar-thumb {
  background: #d3dae3;
  border-radius: 3px;
}

.skeleton-item {
  margin-bottom: 18px;
}

.empty-state {
  flex: 1;
  display: grid;
  place-items: center;
  min-height: 200px;
}
</style>
