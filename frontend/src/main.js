import { createApp } from 'vue'
import axios from 'axios'
import {
  ElAlert, ElButton, ElCard, ElCheckbox, ElDialog, ElDivider, ElEmpty, ElForm,
  ElFormItem, ElIcon, ElInput, ElInputNumber, ElOption, ElSelect, ElSlider,
  ElTable, ElTableColumn, ElTabs, ElTabPane, ElTag, ElUpload,
} from 'element-plus'
import 'element-plus/dist/index.css'
import { Loading } from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'

axios.defaults.withCredentials = true

const app = createApp(App)

app.component('Loading', Loading)

for (const component of [
  ElAlert, ElButton, ElCard, ElCheckbox, ElDialog, ElDivider, ElEmpty, ElForm,
  ElFormItem, ElIcon, ElInput, ElInputNumber, ElOption, ElSelect, ElSlider,
  ElTable, ElTableColumn, ElTabs, ElTabPane, ElTag, ElUpload,
]) {
  app.component(component.name, component)
}
app.use(router)
app.mount('#app')
