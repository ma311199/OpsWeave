<template>
  <el-card shadow="never" class="chat-card">
    <template #header>
      <div class="chat-header">
        <span class="chat-title">Agent Chat</span>
        <el-tag size="small" type="info">WebSocket</el-tag>
      </div>
    </template>

    <div class="chat-messages" ref="messagesContainer">
      <div v-for="(msg, i) in messages" :key="i" :class="['msg-row', msg.type]">
        <div v-if="msg.type === 'thinking'" class="msg-thinking">
          <el-icon class="is-loading"><Loading /></el-icon>
          {{ msg.content }}
        </div>
        <div v-else-if="msg.type === 'tool'" class="msg-tool">
          <el-tag size="small" type="warning">{{ msg.tool }}</el-tag>
          <span>{{ msg.content }}</span>
        </div>
        <div v-else-if="msg.type === 'approval_required'" class="msg-bubble assistant-bubble approval-bubble">
          <div>工具 {{ msg.tool }} 需要人工审批，参数：{{ JSON.stringify(msg.arguments) }}</div>
          <el-button size="small" type="primary" @click="decideApproval(msg.id, true)">批准并执行</el-button>
          <el-button size="small" type="danger" @click="decideApproval(msg.id, false)">拒绝</el-button>
          <div v-if="approvalResults[msg.id]">{{ approvalResults[msg.id] }}</div>
        </div>
        <div v-else-if="msg.type === 'clarify'" class="msg-bubble assistant-bubble clarify-bubble">
          {{ msg.content }}
        </div>
        <div v-else-if="msg.type === 'error'" class="msg-error">
          <el-alert :title="msg.content" type="error" :closable="false" />
        </div>
        <div v-else-if="msg.type === 'user'" class="msg-bubble user-bubble">
          {{ msg.content }}
        </div>
        <div v-else class="msg-bubble assistant-bubble">
          {{ msg.content }}
        </div>
      </div>
    </div>

    <el-input v-model="rememberInput" placeholder="可选：添加一条长期记忆（例如：偏好中文回答）" class="memory-input" />
    <div class="chat-input">
      <el-input
        v-model="input"
        type="textarea"
        :rows="2"
        placeholder="输入运维问题，Ctrl+Enter 发送..."
        @keydown.ctrl.enter="send"
      />
      <el-button type="primary" :loading="loading" @click="send">发送</el-button>
    </div>
  </el-card>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { Loading } from '@element-plus/icons-vue'

const messages = ref([])
const approvalResults = ref({})
const input = ref('')
const rememberInput = ref('')
const loading = ref(false)
const messagesContainer = ref(null)
const conversationId = crypto.randomUUID()
let ws = null

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function connectAndSend(query) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${window.location.host}/api/chat/ws/chat`)

  ws.onopen = () => {
    const remember = rememberInput.value.trim()
    ws.send(JSON.stringify({ query, conversation_id: conversationId, ...(remember ? { remember } : {}) }))
    rememberInput.value = ''
  }

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    messages.value.push(msg)
    scrollToBottom()

    if (msg.type === 'done' || msg.type === 'error') {
      loading.value = false
      if (msg.type === 'done') {
        setTimeout(() => { ws?.close(); ws = null }, 100)
      }
    }
  }

  ws.onclose = () => {
    loading.value = false
  }

  ws.onerror = () => {
    messages.value.push({ type: 'error', content: 'WebSocket 连接失败' })
    loading.value = false
  }
}

async function decideApproval(id, approve) {
  try {
    const response = await fetch(`/api/approvals/${id}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ approve }),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || '审批处理失败')
    approvalResults.value[id] = approve ? `已批准并执行：${JSON.stringify(payload.result)}` : '已拒绝执行'
  } catch (error) {
    approvalResults.value[id] = error.message
  }
}

function send() {
  const query = input.value.trim()
  if (!query || loading.value) return
  const pendingApproval = messages.value.find((item) => item.type === 'approval_required' && !approvalResults.value[item.id])
  if (pendingApproval) return

  messages.value.push({ type: 'user', content: query })
  input.value = ''
  scrollToBottom()

  loading.value = true
  connectAndSend(query)
}
</script>

<style scoped>
.chat-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chat-title {
  font-weight: 600;
  font-size: 15px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #fafafa;
}

.msg-row {
  margin-bottom: 12px;
  display: flex;
}

.msg-row.user {
  justify-content: flex-end;
}

.msg-row.assistant,
.msg-row.answer {
  justify-content: flex-start;
}

.msg-bubble {
  max-width: 75%;
  padding: 10px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.user-bubble {
  background: #409eff;
  color: #fff;
}

.assistant-bubble {
  background: #fff;
  color: #333;
  border: 1px solid #e4e7ed;
}

.msg-thinking {
  color: #909399;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.msg-tool {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #e6a23c;
}

.msg-error {
  width: 100%;
}

.chat-input {
  display: flex;
  gap: 12px;
  padding: 12px 0 0;
}

.chat-input .el-textarea {
  flex: 1;
}
</style>
