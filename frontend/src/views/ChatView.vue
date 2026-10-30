<template>
  <div class="chat-view">
    <ChatPanel :role="currentRole" />
  </div>
</template>

<script setup>
import ChatPanel from '../components/ChatPanel.vue'
import { currentRole } from '../store/role'
</script>

<style scoped>
.chat-view {
  height: 100%;
}
</style>
