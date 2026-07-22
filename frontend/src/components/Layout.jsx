import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { User, TrendingUp, BookOpen, Wallet, Clock, LayoutDashboard, HelpCircle, FileEdit, Download, Users, BarChart3, Settings, Layers } from 'lucide-react'

const iconMap = {
  'profile': User,
  'progress': TrendingUp,
  'subjects': BookOpen,
  'grant-calc': Wallet,
  'history': Clock,
  'teacher-dashboard': LayoutDashboard,
  'questions': HelpCircle,
  'authorial': FileEdit,
  'import': Download,
  'students': Users,
  'groups': Layers,
  'results': BarChart3,
  'analytics': TrendingUp,
  'admin': Settings,
}

const iconStyle = { width: 20, height: 20, strokeWidth: 1.5 }

const studentLinks = [
  { to: '/', label: 'Профиль', icon: 'profile' },
  { to: '/progress', label: 'Прогресс', icon: 'progress' },
  { to: '/subjects', label: 'Предметы', icon: 'subjects' },
  { to: '/grant-calc', label: 'Гранты', icon: 'grant-calc' },
  { to: '/history', label: 'История', icon: 'history' },
]

const teacherLinks = [
  { to: '/teacher', label: 'Дашборд', icon: 'teacher-dashboard' },
  { to: '/subjects', label: 'Предметы', icon: 'subjects' },
  { to: '/teacher/questions', label: 'Вопросы', icon: 'questions' },
  { to: '/teacher/tests/authorial', label: 'Авторские', icon: 'authorial' },
  { to: '/teacher/import/google-forms', label: 'Импорт', icon: 'import' },
  { to: '/teacher/students', label: 'Ученики', icon: 'students' },
  { to: '/teacher/groups', label: 'Группы', icon: 'groups' },
  { to: '/teacher/tests', label: 'Результаты', icon: 'results' },
  { to: '/teacher/analytics', label: 'Аналитика', icon: 'analytics' },
]

const adminLink = { to: '/admin', label: 'Админ', icon: 'admin' }

function NavIcon({ name }) {
  const Icon = iconMap[name]
  return Icon ? <Icon style={iconStyle} /> : null
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const isActive = (to) => {
    const path = location.pathname
    if (to === '/teacher/tests') {
      return path === '/teacher/tests' || path === '/teacher/tests/' ||
        (path.startsWith('/teacher/tests/') && !path.startsWith('/teacher/tests/authorial'))
    }
    return to === '/' ? path === '/' : path.startsWith(to)
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const baseLinks = user?.role === 'teacher' || user?.role === 'admin' ? teacherLinks : studentLinks
  const links = user?.role === 'admin' ? [...baseLinks, adminLink] : baseLinks

  const initials = user?.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.username?.[0]?.toUpperCase() || '?'

  const roleLabel = user?.role === 'teacher' ? 'Учитель' : user?.role === 'admin' ? 'Админ' : 'Ученик'

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-logo"><img src="/assets/logo.png" alt="" className="sidebar-logo-img" /></div>
        <nav className="sidebar-nav">
          {links.map(link => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === '/' || link.to === '/teacher'}
              className={`sidebar-link ${isActive(link.to) ? 'active' : ''}`}
            >
              <span className="sidebar-link-icon"><NavIcon name={link.icon} /></span>
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="sidebar-avatar">{initials}</div>
            <div>
              <div className="sidebar-username">{user?.full_name || user?.username}</div>
              <div className="sidebar-role">{roleLabel}</div>
            </div>
          </div>
          <button className="btn btn-outline sidebar-logout" onClick={handleLogout}>
            Выйти
          </button>
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
      <nav className="mobile-tabbar">
        {links.map(link => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === '/' || link.to === '/teacher'}
            className={`mobile-tab ${isActive(link.to) ? 'active' : ''}`}
          >
            <span className="mobile-tab-icon"><NavIcon name={link.icon} /></span>
            {link.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
