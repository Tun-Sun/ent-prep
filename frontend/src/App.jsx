import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'

function TeacherRoute({ children }) {
  const { user } = useAuth()
  if (!user || (user.role !== 'teacher' && user.role !== 'admin')) {
    return <Navigate to="/" replace />
  }
  return children
}

// Auth
import LoginPage from './pages/auth/LoginPage'
import RegisterPage from './pages/auth/RegisterPage'

// Student
import StudentDashboardPage from './pages/student/DashboardPage'
import SubjectListPage from './pages/student/SubjectListPage'
import TestPage from './pages/student/TestPage'
import ResultsPage from './pages/student/ResultsPage'
import HistoryPage from './pages/student/HistoryPage'
import GrantCalcPage from './pages/student/GrantCalcPage'
import LeaderboardPage from './pages/student/LeaderboardPage'
import SettingsPage from './pages/student/SettingsPage'

// Teacher
import TeacherDashboardPage from './pages/teacher/DashboardPage'

import StudentsPage from './pages/teacher/StudentsPage'
import GroupsPage from './pages/teacher/GroupsPage'
import AnalyticsPage from './pages/teacher/AnalyticsPage'
import QuestionsPage from './pages/teacher/QuestionsPage'
import ImportPage from './pages/teacher/ImportPage'
import GoogleFormsImportPage from './pages/teacher/GoogleFormsImportPage'
import TestHistoryPage from './pages/teacher/TestHistoryPage'
import TestResultPage from './pages/teacher/TestResultPage'
import TestPreviewPage from './pages/teacher/TestPreviewPage'
import AuthorialTestsPage from './pages/teacher/AuthorialTestsPage'
import AuthorialTestEditorPage from './pages/teacher/AuthorialTestEditorPage'
import AdminPanelPage from './pages/teacher/AdminPanelPage'
import TeacherSettingsPage from './pages/teacher/TeacherSettingsPage'

function HomePage() {
  const { user, loading } = useAuth()
  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (!user) return <Navigate to="/login" replace />
  if (user.role === 'teacher' || user.role === 'admin') return <Navigate to="/teacher" replace />
  return <StudentDashboardPage />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Все авторизованные маршруты в одном Layout */}
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<HomePage />} />
        <Route path="subjects" element={<SubjectListPage />} />
        <Route path="progress" element={<StudentDashboardPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="grant-calc" element={<GrantCalcPage />} />
        <Route path="leaderboard" element={<LeaderboardPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="test/start/:subjectId" element={<TestPage />} />
        <Route path="test/ent" element={<TestPage />} />
        <Route path="test/result/:sessionId" element={<ResultsPage />} />

        {/* Teacher / Admin */}
        <Route path="teacher" element={<TeacherRoute><TeacherDashboardPage /></TeacherRoute>} />
        <Route path="teacher/questions" element={<TeacherRoute><QuestionsPage /></TeacherRoute>} />
        <Route path="teacher/import" element={<TeacherRoute><ImportPage /></TeacherRoute>} />
        <Route path="teacher/import/google-forms" element={<TeacherRoute><GoogleFormsImportPage /></TeacherRoute>} />

        <Route path="teacher/students" element={<TeacherRoute><StudentsPage /></TeacherRoute>} />
        <Route path="teacher/groups" element={<TeacherRoute><GroupsPage /></TeacherRoute>} />
        <Route path="teacher/analytics" element={<TeacherRoute><AnalyticsPage /></TeacherRoute>} />
        <Route path="teacher/tests/preview" element={<TeacherRoute><TestPreviewPage /></TeacherRoute>} />
        <Route path="teacher/tests/authorial/:formId/edit" element={<TeacherRoute><AuthorialTestEditorPage /></TeacherRoute>} />
        <Route path="teacher/tests/authorial" element={<TeacherRoute><AuthorialTestsPage /></TeacherRoute>} />
        <Route path="teacher/tests" element={<TeacherRoute><TestHistoryPage /></TeacherRoute>} />
        <Route path="teacher/tests/:sessionId" element={<TeacherRoute><TestResultPage /></TeacherRoute>} />
        <Route path="teacher/settings" element={<TeacherRoute><TeacherSettingsPage /></TeacherRoute>} />
        <Route path="admin" element={<TeacherRoute><AdminPanelPage /></TeacherRoute>} />
      </Route>

      <Route path="*" element={<HomePage />} />
    </Routes>
  )
}