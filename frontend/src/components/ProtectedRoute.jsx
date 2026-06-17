import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children, requiredRole }) {
  const { user, loading } = useAuth()

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (!user) return <Navigate to="/login" replace />
  // При несовпадении роли — отправляем на главную страницу своей роли (без зацикливания)
  if (requiredRole && user.role !== requiredRole) {
    const homePath = user.role === 'teacher' ? '/teacher' : '/'
    // Если уже идём туда — не зацикливаемся, пускаем (не должно случаться, но для надёжности)
    return <Navigate to={homePath} replace />
  }

  return children
}
