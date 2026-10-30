<template>
  <div class="app-container">
    <header class="app-header">
      <div class="header-left">
        <h1 class="app-title">OpsWeave</h1>
        <span class="app-subtitle">Agentic RAG for Operations</span>
      </div>
      <div class="header-right">
        <el-select v-model="currentRole" size="small" style="width: 150px">
          <el-option label="Admin" value="admin" />
          <el-option label="Ops Engineer" value="ops_engineer" />
          <el-option label="Viewer" value="viewer" />
        </el-select>
        <div class="nav-links">
          <router-link to="/chat" class="nav-link" :class="{ active: activeMenu === 'chat' }">Agent Chat</router-link>
          <router-link to="/retrieval" class="nav-link" :class="{ active: activeMenu === 'retrieval' }">知识库检索</router-link>
          <router-link to="/knowledge" class="nav-link" :class="{ active: activeMenu === 'knowledge' }">知识库管理</router-link>
          <router-link to="/config" class="nav-link" :class="{ active: activeMenu === 'config' }">系统配置</router-link>
        </div>
      </div>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { currentRole } from './store/role'

const route = useRoute()
const activeMenu = computed(() => {
  if (route.path.startsWith('/retrieval')) return 'retrieval'
  if (route.path.startsWith('/knowledge')) return 'knowledge'
  if (route.path.startsWith('/config')) return 'config'
  return 'chat'
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Helvetica Neue', Arial, sans-serif; }

.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  background: #1a1a2e;
  color: #fff;
  height: 56px;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.app-title {
  font-size: 20px;
  font-weight: 700;
  color: #4fc3f7;
}

.app-subtitle {
  font-size: 12px;
  color: #888;
}

.nav-links {
  display: flex;
  gap: 4px;
}

.nav-link {
  padding: 8px 16px;
  text-decoration: none;
  color: #ccc;
  font-size: 14px;
  border-radius: 6px;
  transition: all 0.2s;
}

.nav-link:hover {
  color: #fff;
  background: rgba(79, 195, 247, 0.1);
}

.nav-link.active {
  color: #4fc3f7;
  background: rgba(79, 195, 247, 0.15);
}

.app-main {
  flex: 1;
  overflow: hidden;
  padding: 16px;
  background: #f0f2f5;
}
</style>
