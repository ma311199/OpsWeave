<template>
  <el-card shadow="never" class="chat-card">
    <template #header>
      <div class="chat-header">
        <div class="header-title-group">
          <div class="header-icon"><el-icon :size="20"><Monitor /></el-icon></div>
          <div class="header-texts">
            <span class="chat-title">Agent Chat</span>
            <span class="chat-subtitle">Agentic RAG 运维助手</span>
          </div>
        </div>
        <div class="header-status" :class="loading ? 'is-busy' : 'is-online'">
          <span class="status-dot"></span>
          <span class="status-text">{{ loading ? '思考中' : '在线' }}</span>
        </div>
      </div>
    </template>

    <div class="chat-messages" ref="messagesContainer">
      <div v-if="visibleMessages.length === 0" class="welcome">
        <div class="welcome-icon">🤖</div>
        <h3 class="welcome-title">你好，我是 OpsWeave 运维助手</h3>
        <p class="welcome-desc">我可以检索知识库解答问题，也可以调用运维工具，敏感操作会先请求你的审批。</p>
        <div class="suggestions">
          <div v-for="s in suggestions" :key="s" class="suggestion-item" @click="useSuggestion(s)">
            <el-icon><ChatDotRound /></el-icon>
            <span>{{ s }}</span>
          </div>
        </div>
      </div>

      <div v-for="(msg, i) in visibleMessages" :key="i" :class="['msg-row', msg.type]">
        <div v-if="msg.type === 'thinking'" class="msg-thinking">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ msg.content }}</span>
        </div>

        <template v-else-if="msg.type === 'tool'">
          <div class="avatar bot-avatar"><el-icon><Tools /></el-icon></div>
          <div class="msg-tool">
            <div class="tool-head">
              <el-icon class="tool-icon"><Tools /></el-icon>
              <span class="tool-name">{{ msg.tool }}</span>
              <el-tag size="small" type="warning" effect="plain" round>工具调用</el-tag>
            </div>
            <div class="tool-content">{{ msg.content }}</div>
          </div>
        </template>

        <template v-else-if="msg.type === 'approval_required'">
          <div class="avatar bot-avatar"><el-icon><Tools /></el-icon></div>
          <div class="msg-bubble assistant-bubble approval-bubble">
            <div class="approval-head">
              <el-icon><Warning /></el-icon>
              <span>工具「{{ msg.tool }}」需要人工审批</span>
            </div>
            <div class="approval-args">{{ JSON.stringify(msg.arguments, null, 2) }}</div>
            <div class="approval-actions">
              <el-button size="small" type="primary" @click="decideApproval(msg.id, true)">批准并执行</el-button>
              <el-button size="small" type="danger" plain @click="decideApproval(msg.id, false)">拒绝</el-button>
            </div>
            <div v-if="approvalResults[msg.id]" :class="['approval-result', approvalResults[msg.id].includes('已批准') ? 'ok' : 'no']">
              {{ approvalResults[msg.id] }}
            </div>
          </div>
        </template>

        <template v-else-if="msg.type === 'clarify'">
          <div class="avatar bot-avatar"><el-icon><ChatDotRound /></el-icon></div>
          <div class="msg-bubble assistant-bubble clarify-bubble">
            <div class="clarify-head">
              <el-icon><QuestionFilled /></el-icon>
              <span>需要澄清</span>
            </div>
            <div>{{ msg.content }}</div>
          </div>
        </template>

        <div v-else-if="msg.type === 'error'" class="msg-error">
          <el-alert :title="msg.content" type="error" :closable="false" show-icon />
        </div>

        <template v-else-if="msg.type === 'user'">
          <div class="avatar user-avatar"><el-icon><User /></el-icon></div>
          <div class="msg-bubble user-bubble">{{ msg.content }}</div>
        </template>

        <template v-else>
          <div class="avatar bot-avatar"><el-icon><ChatDotRound /></el-icon></div>
          <div class="msg-bubble assistant-bubble">{{ msg.content }}</div>
        </template>
      </div>
    </div>

    <div class="chat-footer">
      <el-input v-model="rememberInput" class="memory-input" placeholder="可选：添加一条长期记忆（例如：偏好中文回答）">
        <template #prefix><el-icon><Collection /></el-icon></template>
      </el-input>
      <div class="chat-input">
        <el-input
          v-model="input"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="输入运维问题，Ctrl+Enter 发送..."
          @keydown.ctrl.enter="send"
        />
        <div class="send-wrap">
          <el-button type="primary" class="send-btn" :loading="loading" :disabled="!input.trim() || loading" @click="send">
            <el-icon v-if="!loading" style="margin-right: 4px"><Promotion /></el-icon>
            <span>发送</span>
          </el-button>
          <span class="send-hint">Ctrl + Enter</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, nextTick, computed } from 'vue'
import { Loading, Monitor, Tools, Warning, ChatDotRound, QuestionFilled, User, Collection, Promotion } from '@element-plus/icons-vue'

const messages = ref([])
const approvalResults = ref({})
const input = ref('')
const rememberInput = ref('')
const loading = ref(false)
const messagesContainer = ref(null)
const conversationId = crypto.randomUUID()
let ws = null

const suggestions = [
  '检索知识库中关于服务部署的最佳实践',
  '数据库连接池耗尽该如何排查？',
  '帮我总结一下告警处理流程',
]

// done 消息仅用于结束会话，无展示内容，过滤掉避免渲染空气泡
const visibleMessages = computed(() => messages.value.filter((m) => m.type !== 'done'))

function useSuggestion(text) {
  input.value = text
}

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
  border-radius: 12px;
  border: 1px solid #e8ecf1;
  box-shadow: 0 2px 12px rgba(16, 24, 40, 0.04);
  overflow: hidden;
}

.chat-card :deep(.el-card__header) {
  padding: 12px 20px;
  border-bottom: 1px solid #eef1f5;
}

.chat-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-title-group {
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

.chat-title {
  font-weight: 700;
  font-size: 15px;
  color: #1f2d3d;
}

.chat-subtitle {
  font-size: 12px;
  color: #8a94a6;
}

.header-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #8a94a6;
  background: #f4f6fa;
  border: 1px solid #e8ecf1;
  padding: 4px 10px;
  border-radius: 999px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.header-status.is-online .status-dot {
  background: #22c55e;
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.15);
}

.header-status.is-busy .status-dot {
  background: #f59e0b;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.15);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: linear-gradient(180deg, #f7f9fc, #f2f5f9);
}

.chat-messages::-webkit-scrollbar {
  width: 6px;
}

.chat-messages::-webkit-scrollbar-thumb {
  background: #d3dae3;
  border-radius: 3px;
}

.chat-messages::-webkit-scrollbar-thumb:hover {
  background: #b8c2cf;
}

.welcome {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 20px;
}

.welcome-icon {
  font-size: 44px;
  margin-bottom: 12px;
}

.welcome-title {
  font-size: 17px;
  font-weight: 700;
  color: #1f2d3d;
  margin-bottom: 6px;
}

.welcome-desc {
  font-size: 13px;
  color: #8a94a6;
  max-width: 420px;
  margin-bottom: 20px;
  line-height: 1.6;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid #e2e8f0;
  color: #475569;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.suggestion-item:hover {
  border-color: #4fc3f7;
  color: #2563eb;
  box-shadow: 0 2px 8px rgba(79, 195, 247, 0.2);
}

.msg-row {
  margin-bottom: 16px;
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.msg-row.user {
  flex-direction: row-reverse;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 15px;
}

.user-avatar {
  background: linear-gradient(135deg, #4fc3f7, #2563eb);
  color: #fff;
}

.bot-avatar {
  background: #fff;
  color: #5b7ba8;
  border: 1px solid #dbe4ef;
}

.msg-bubble {
  max-width: 72%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.user-bubble {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: #fff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.2);
}

.assistant-bubble {
  background: #fff;
  color: #2c3e50;
  border: 1px solid #e4e9f0;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 4px rgba(16, 24, 40, 0.05);
}

.msg-thinking {
  color: #8a94a6;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 999px;
  border: 1px dashed #d5dde8;
  width: fit-content;
}

.msg-tool {
  max-width: 72%;
  background: #fffdf5;
  border: 1px solid #f3e3bb;
  border-left: 3px solid #e6a23c;
  border-radius: 10px;
  padding: 9px 12px;
}

.tool-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.tool-icon {
  color: #e6a23c;
}

.tool-name {
  font-weight: 600;
  font-size: 13px;
  color: #92702c;
  font-family: monospace;
}

.tool-content {
  font-size: 13px;
  color: #7a6a45;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.approval-bubble {
  border-color: #f3d19e;
  background: #fffbf2;
}

.approval-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  color: #b88230;
  font-weight: 600;
  font-size: 13px;
}

.approval-args {
  background: #f8f6f0;
  border: 1px solid #eee4cc;
  border-radius: 6px;
  padding: 8px 10px;
  font-family: monospace;
  font-size: 12px;
  color: #6b5b3e;
  max-height: 140px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin-bottom: 10px;
}

.approval-actions {
  display: flex;
  gap: 8px;
}

.approval-result {
  margin-top: 8px;
  font-size: 12px;
}

.approval-result.ok {
  color: #16a34a;
}

.approval-result.no {
  color: #dc2626;
}

.clarify-bubble {
  border-color: #dbe9ff;
  background: #f5f9ff;
}

.clarify-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #4a7dbe;
  font-weight: 600;
  margin-bottom: 4px;
}

.msg-error {
  width: 100%;
}

.chat-footer {
  border-top: 1px solid #eef1f5;
  background: #fff;
  padding: 12px 16px 10px;
}

.memory-input {
  margin-bottom: 8px;
}

.chat-input {
  display: flex;
  gap: 12px;
  align-items: stretch;
}

.chat-input .el-textarea {
  flex: 1;
}

.send-wrap {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: center;
  gap: 4px;
}

.send-btn {
  height: 100%;
  min-height: 44px;
  border-radius: 10px;
  font-weight: 600;
}

.send-hint {
  font-size: 11px;
  color: #aab3c0;
  white-space: nowrap;
}
</style>
