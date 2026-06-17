import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'

// Auth
import LoginPage from './pages/auth/LoginPage'
import RegisterPage from './pages/auth/RegisterPage'

// Student
import StudentDashboardPage from './pages/student/DashboardPage'
import SubjectListPage from './pages/student/SubjectListPage'
import TestPage from './pages/student/TestPage'
import ResultsPage from './pages/student/ResultsPage'
import HistoryPage from './pages/student/HistoryPage'

// Teacher
import TeacherDashboardPage from './pages/teacher/DashboardPage'
import StudentsPage from './pages/teacher/StudentsPage'
import AnalyticsPage from './pages/teacher/AnalyticsPage'
import QuestionsPage from './pages/teacher/QuestionsPage'
import ImportPage from './pages/teacher/ImportPage'

// Главная страница: решает, кого показывать, по роли
function HomePage() {
  const { user, loading } = useAuth()
  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (!user) return <Navigate to="/login" replace />
  if (user.role === 'teacher') return <Navigate to="/teacher" replace />
  return <StudentDashboardPage />
}

export default function App() {
  return (
    <Routes>
      {/* Auth */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Корень — доступен любому авторизованному, сам решает что показать */}
      <Route element={
        <ProtectedRoute>
          <Layout />
        </ProtectedRoute>
      }>
        <Route index element={<HomePage />} />
      </Route>

      {/* Student routes */}
      <Route element={
        <ProtectedRoute requiredRole="student">
          <Layout />
        </ProtectedRoute>
      }>
        <Route path="subjects" element={<SubjectListPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="test/start/:subjectId" element={<TestPage />} />
        <Route path="test/result/:sessionId" element={<ResultsPage />} />
      </Route>

      {/* Teacher routes */}
      <Route element={
        <ProtectedRoute requiredRole="teacher">
          <Layout />
        </ProtectedRoute>
      }>
        <Route path="teacher" element={<TeacherDashboardPage />} />
        <Route path="teacher/questions" element={<QuestionsPage />} />
        <Route path="teacher/import" element={<ImportPage />} />
        <Route path="teacher/students" element={<StudentsPage />} />
        <Route path="teacher/analytics" element={<AnalyticsPage />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<HomePage />} />
    </Routes>
  )
}
