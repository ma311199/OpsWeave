<template>
  <div class="retrieval-view">
    <RetrievalPanel :role="currentRole" />
  </div>
</template>

<script setup>
import RetrievalPanel from '../components/RetrievalPanel.vue'
import { currentRole } from '../store/role'
</script>

<style scoped>
.retrieval-view {
  height: 100%;
}
</style>
