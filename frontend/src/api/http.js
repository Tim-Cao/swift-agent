import axios from 'axios'

// 所有 /api 请求由 Vite dev server 代理到后端 :8000
const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

export default http
