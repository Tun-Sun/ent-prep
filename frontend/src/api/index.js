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
  updateProfile: (data) => api.patch('/auth/profile/', data),
  uploadAvatar: (file) => {
    const fd = new FormData()
    fd.append('avatar', file)
    return api.patch('/auth/profile/', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  updateProfileSubjects: (subjectIds) => api.put('/auth/profile/subjects/', { profile_subjects: subjectIds }),
  clearHistory: () => api.delete('/auth/profile/history/'),
  deleteAccount: (password) => api.delete('/auth/profile/account/', { data: { password } }),
  changePassword: (oldPassword, newPassword) => api.post('/auth/login/change-password/', { old_password: oldPassword, new_password: newPassword }),
  resetStudentPassword: (studentId, password) => api.post(`/auth/students/${studentId}/reset-password/`, password ? { password } : {}),
}

// Subjects
export const subjectsAPI = {
  list: () => api.get('/subjects/'),
  /** Публичный список для экрана регистрации (без JWT) */
  forRegistration: () => api.get('/subjects/for-registration/'),
  retrieve: (id) => api.get(`/subjects/${id}/`),
  minimal: () => api.get('/subjects/minimal/'),
  topics: (subjectId) => api.get(`/subjects/${subjectId}/topics/`),
  createSubject: (data) => api.post('/subjects/', data),
  toggleVisibility: (id) => api.post(`/subjects/${id}/toggle_visibility/`),
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
  // Импорт по ссылке на Google Form
  importFromUrl: (data) => api.post('/import/google-forms-url/', data),
  // Предпросмотр по ссылке (dry-run)
  previewFromUrl: (data) => api.post('/import/google-forms-url/?dry_run=1', data),
}

// Tests
export const testsAPI = {
  start: (data) => api.post('/tests/start/', data),
  startEnt: (data) => api.post('/tests/start-ent/', data),
  answer: (sessionId, data) => api.post(`/tests/${sessionId}/answer/`, data),
  answerBulk: (sessionId, data) => api.post(`/tests/${sessionId}/answers/bulk/`, data),
  finish: (sessionId) => api.post(`/tests/${sessionId}/finish/`),
  state: (sessionId) => api.get(`/tests/${sessionId}/state/`),
  result: (sessionId) => api.get(`/tests/${sessionId}/result/`),
  history: () => api.get('/tests/history/'),
  // Teacher endpoints
  teacherHistory: (params) => api.get('/tests/teacher/history/', { params }),
  teacherResult: (sessionId) => api.get(`/tests/teacher/result/${sessionId}/`),
  aiExplain: (sessionId, data) => api.post(`/tests/${sessionId}/ai-explain/`, data),
  preview: (data) => api.post('/tests/preview/', data),
  authorialTests: () => api.get('/tests/authorial-tests/'),
  authorialTestQuestions: (formId) => api.get(`/tests/authorial-tests/${formId}/questions/`),
  deleteAuthorialTest: (formId) => api.delete(`/tests/authorial-tests/${formId}/`),
  startDuel: (duelId) => api.post(`/gamification/duels/${duelId}/play/`),
}

// Dashboard
export const dashboardAPI = {
  student: () => api.get('/dashboard/student/'),
  teacher: (params) => api.get('/dashboard/teacher/', { params }),
  teacherStudents: (params = {}) => api.get('/dashboard/teacher/students/', { params }),
  teacherAnalytics: (params) => api.get('/dashboard/teacher/analytics/', { params }),
  leaderboard: (params) => api.get('/dashboard/leaderboard/', { params }),
  dashboardSubjects: () => api.get('/dashboard/teacher/dashboard-subjects/'),
  updateDashboardSubjects: (subjectIds) => api.put('/dashboard/teacher/dashboard-subjects/', { subject_ids: subjectIds }),
  weakTopics: () => api.get('/dashboard/student/weak-topics/'),
  entForecast: () => api.get('/dashboard/student/ent-forecast/'),
  studentReportPdf: (studentId) => api.get(`/dashboard/teacher/students/${studentId}/report.pdf/`, { responseType: 'blob' }),
}

// Gamification
export const gamificationAPI = {
  achievements: () => api.get('/gamification/achievements/'),
  duels: () => api.get('/gamification/duels/'),
  createDuel: (data) => api.post('/gamification/duels/', data),
  respondDuel: (duelId, action) => api.post(`/gamification/duels/${duelId}/respond/`, { action }),
  duelOpponents: (search) => api.get('/gamification/duels/opponents/', { params: search ? { search } : {} }),
}

export const grantCalcAPI = {
  calculate: (params) => api.get('/grant-calc/', { params }),
  types: () => api.get('/grant-calc/types/'),
}

export const adminAPI = {
  users: (params) => api.get('/auth/admin/users/', { params }),
  updateUser: (id, data) => api.patch(`/auth/admin/users/${id}/`, data),
  deleteUser: (id) => api.delete(`/auth/admin/users/${id}/delete/`),
  settings: () => api.get('/auth/admin/settings/'),
  updateSetting: (id, data) => api.patch(`/auth/admin/settings/${id}/`, data),
  createSetting: (data) => api.post('/auth/admin/settings/', data),
}

// Groups (учительские группы)
export const groupsAPI = {
  list: () => api.get('/auth/groups/'),
  create: (name) => api.post('/auth/groups/', { name }),
  detail: (id) => api.get(`/auth/groups/${id}/`),
  update: (id, data) => api.patch(`/auth/groups/${id}/`, data),
  delete: (id) => api.delete(`/auth/groups/${id}/`),
  addStudents: (id, studentIds) => api.post(`/auth/groups/${id}/students/`, { student_ids: studentIds }),
  removeStudent: (id, studentId) => api.delete(`/auth/groups/${id}/students/?student_id=${studentId}`),
  searchStudents: (query, groupId) => {
    let url = `/auth/students/search/?search=${query}`
    if (groupId) url += `&group_id=${groupId}`
    return api.get(url)
  },
  createStudent: (data) => api.post('/auth/students/create/', data),
  updateStudentSubjects: (studentId, subjectIds) =>
    api.put(`/auth/students/${studentId}/subjects/`, { profile_subjects: subjectIds }),
}

export default api
