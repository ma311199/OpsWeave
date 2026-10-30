import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/chat',
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('./views/ChatView.vue'),
    meta: { title: 'Agent Chat' },
  },
  {
    path: '/retrieval',
    name: 'Retrieval',
    component: () => import('./views/RetrievalView.vue'),
    meta: { title: '知识库检索' },
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => import('./views/KnowledgeView.vue'),
    meta: { title: '知识库管理' },
  },
  {
    path: '/config',
    name: 'Config',
    component: () => import('./views/ConfigView.vue'),
    meta: { title: '系统配置' },
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
