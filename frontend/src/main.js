import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'bootstrap-icons/font/bootstrap-icons.css'
import './styles/notion.css'
import App from './App.vue'

const app = createApp(App)
app.use(createPinia())
app.use(ElementPlus)
app.mount('#app')
