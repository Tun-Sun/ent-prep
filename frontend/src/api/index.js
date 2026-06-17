import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Добавляем JWT токен к каждому запросу
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Обновляем токен при 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const res = await axios.post('/api/auth/refresh/', { refresh })
          localStorage.setItem('access_token', res.data.access)
          originalRequest.headers.Authorization = `Bearer ${res.data.access}`
          return api(originalRequest)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  }
)

// Auth
export const authAPI = {
  login: (data) => api.post('/auth/login/', data),
  register: (data) => api.post('/auth/register/', data),
  profile: () => api.get('/auth/profile/'),
}

// Subjects
export const subjectsAPI = {
  list: () => api.get('/subjects/'),
  retrieve: (id) => api.get(`/subjects/${id}/`),
  topics: (subjectId) => api.get(`/subjects/${subjectId}/topics/`),
  createSubject: (data) => api.post('/subjects/', data),
  // Topics
  listTopics: (subjectId) => api.get(`/topics/?subject=${subjectId}`),
  createTopic: (data) => api.post('/topics/', data),
}

// Questions (CRUD для учителя)
export const questionsAPI = {
  list: (params) => api.get('/questions/', { params }),
  retrieve: (id) => api.get(`/questions/${id}/`),
  create: (data) => api.post('/questions/', data),
  update: (id, data) => api.put(`/questions/${id}/`, data),
  delete: (id) => api.delete(`/questions/${id}/`),
}

// Импорт Excel
export const importAPI = {
  // Скачивание шаблона (возвращает blob)
  template: () => api.get('/import/template/', { responseType: 'blob' }),
  // Загрузка файла
  upload: (file, subjectId) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('subject_id', subjectId)
    return api.post('/import/excel/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}

// Tests
export const testsAPI = {
  start: (data) => api.post('/tests/start/', data),
  answer: (sessionId, data) => api.post(`/tests/${sessionId}/answer/`, data),
  finish: (sessionId) => api.post(`/tests/${sessionId}/finish/`),
  result: (sessionId) => api.get(`/tests/${sessionId}/result/`),
  history: () => api.get('/tests/history/'),
}

// Dashboard
export const dashboardAPI = {
  student: () => api.get('/dashboard/student/'),
  teacher: () => api.get('/dashboard/teacher/'),
  teacherStudents: () => api.get('/dashboard/teacher/students/'),
  teacherAnalytics: () => api.get('/dashboard/teacher/analytics/'),
}

export default api
