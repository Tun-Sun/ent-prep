import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const studentLinks = [
    { to: '/', label: 'Дашборд', icon: '📊', short: 'Главная' },
    { to: '/subjects', label: 'Предметы', icon: '📚', short: 'Тесты' },
    { to: '/history', label: 'История тестов', icon: '📝', short: 'История' },
  ]

  const teacherLinks = [
    { to: '/teacher', label: 'Дашборд', icon: '📊', short: 'Главная' },
    { to: '/teacher/questions', label: 'Вопросы', icon: '📝', short: 'Вопросы' },
    { to: '/teacher/import', label: 'Импорт Excel', icon: '📥', short: 'Импорт' },
    { to: '/teacher/students', label: 'Ученики', icon: '👥', short: 'Ученики' },
    { to: '/teacher/analytics', label: 'Аналитика', icon: '📈', short: 'Аналитика' },
  ]

  const links = user?.role === 'teacher' ? teacherLinks : studentLinks

  const initials = user?.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.username?.[0]?.toUpperCase() || '?'

  const roleName = user?.role === 'teacher' ? 'Учитель' : 'Ученик'

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-logo">🎓 ENT Prep</div>
        <nav className="sidebar-nav">
          {links.map(link => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === '/'}
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            >
              <span className="sidebar-link-icon">{link.icon}</span>
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="sidebar-avatar">{initials}</div>
            <div>
              <div className="sidebar-username">{user?.full_name || user?.username}</div>
              <div className="sidebar-role">{roleName}</div>
            </div>
          </div>
          <button className="btn btn-outline" style={{ width: '100%' }} onClick={handleLogout}>
            Выйти
          </button>
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>

      {/* Мобильное нижнее меню (видно только на телефонах) */}
      <nav className="mobile-tabbar">
        {links.map(link => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === '/'}
            className={({ isActive }) => `mobile-tab ${isActive ? 'active' : ''}`}
          >
            <span className="mobile-tab-icon">{link.icon}</span>
            {link.short}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
