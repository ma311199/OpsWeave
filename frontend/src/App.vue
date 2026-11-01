<template>
  <div class="app-container">
    <header class="app-header">
      <div class="header-left">
        <h1 class="app-title">OpsWeave</h1>
        <span class="app-subtitle">Agentic RAG for Operations</span>
      </div>
      <div v-if="user" class="header-right">
        <span>{{ user.username }} ({{ user.role === 'admin' ? '管理员' : '普通用户' }})</span>
        <div class="nav-links">
          <router-link to="/chat" class="nav-link" :class="{ active: activeMenu === 'chat' }">Agent Chat</router-link>
          <router-link to="/retrieval" class="nav-link" :class="{ active: activeMenu === 'retrieval' }">知识库检索</router-link>
          <router-link to="/knowledge" class="nav-link" :class="{ active: activeMenu === 'knowledge' }">知识库管理</router-link>
          <router-link v-if="user.role === 'admin'" to="/config" class="nav-link" :class="{ active: activeMenu === 'config' }">系统配置</router-link>
        </div>
        <el-button size="small" @click="logout">退出</el-button>
      </div>
    </header>
    <main v-if="user" class="app-main">
      <router-view />
    </main>
    <main v-else class="auth-main">
      <el-card class="auth-card">
        <h2>{{ registering ? '创建普通用户' : '登录 OpsWeave' }}</h2>
        <p v-if="registering" class="auth-note">公开注册仅创建普通用户账号。</p>
        <el-input v-model="form.username" placeholder="用户名" autocomplete="username" />
        <el-input v-model="form.password" type="password" show-password :placeholder="registering ? '密码（至少 8 位）' : '密码'" autocomplete="current-password" @keyup.enter="submitAuth" />
        <el-button type="primary" :loading="busy" @click="submitAuth">{{ registering ? '注册' : '登录' }}</el-button>
        <el-button link @click="registering = !registering">{{ registering ? '已有账号？返回登录' : '创建新账号' }}</el-button>
      </el-card>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'

const user = ref(null)
const registering = ref(false)
const busy = ref(false)
const form = reactive({ username: '', password: '' })

async function loadUser() {
  try { user.value = (await axios.get('/api/auth/me')).data } catch { user.value = null }
}

async function submitAuth() {
  busy.value = true
  try {
    const endpoint = registering.value ? '/api/auth/register' : '/api/auth/login'
    await axios.post(endpoint, form)
    if (registering.value) {
      registering.value = false
      ElMessage.success('注册成功，请登录')
    } else {
      await loadUser()
    }
    form.password = ''
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '操作失败')
  } finally { busy.value = false }
}

async function logout() {
  await axios.post('/api/auth/logout')
  user.value = null
}

onMounted(loadUser)
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

.auth-main {
  flex: 1;
  display: grid;
  place-items: center;
  background: #f0f2f5;
}
.auth-card { width: 360px; }
.auth-card h2 { margin-bottom: 20px; }
.auth-note { margin: -8px 0 14px; color: #667085; font-size: 13px; }
.auth-card .el-input, .auth-card .el-button { margin-bottom: 12px; width: 100%; }

.app-main {
  flex: 1;
  overflow: hidden;
  padding: 16px;
  background: #f0f2f5;
}
</style>
