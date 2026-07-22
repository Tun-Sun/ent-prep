import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children, requiredRole }) {
  const { user, loading } = useAuth()

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (!user) return <Navigate to="/login" replace />
  // Админ имеет доступ ко всем маршрутам учителя
  const effectiveRole = user.role === 'admin' ? 'teacher' : user.role
  if (requiredRole && effectiveRole !== requiredRole) {
    const homePath = user.role === 'teacher' ? '/teacher' : '/'
    return <Navigate to={homePath} replace />
  }

  return children
}
