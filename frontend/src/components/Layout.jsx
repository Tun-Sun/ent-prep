import { useEffect, useRef } from 'react'
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useViewMode } from '../context/ViewModeContext'
import { User, TrendingUp, BookOpen, Library, ScanText, Wallet, Clock, LayoutDashboard, HelpCircle, FileEdit, Download, Users, BarChart3, Settings, Layers, Swords, ClipboardList } from 'lucide-react'

const iconMap = {
  'profile': User,
  'progress': TrendingUp,
  'subjects': BookOpen,
  'grant-calc': Wallet,
  'history': Clock,
  'duels': Swords,
  'teacher-dashboard': LayoutDashboard,
  'topics': Layers,
  'questions': HelpCircle,
  'book-bank': Library,
  'book-ingest': ScanText,
  'assign': ClipboardList,
  'authorial': FileEdit,
  'import': Download,
  'students': Users,
  'groups': Layers,
  'results': BarChart3,
  'analytics': TrendingUp,
  'admin': Settings,
}

const iconStyle = { width: 20, height: 20, strokeWidth: 1.5 }

// Кабинет ученика 5–11 классов. Урок, назначенный тренером, — главное, за чем
// ребёнок пришёл, поэтому он первым. Гранты и дуэли — игры одиннадцатиклассников:
// пятикласснику их не показывают.
// `short` — подпись на телефоне: полная строка в панель не влезает.
const studentSections = (grade) => {
  const main = [
    { to: '/assignments', label: 'Мои уроки', short: 'Уроки', icon: 'assign' },
    { to: '/subjects', label: 'Тренажёр', short: 'Тренажёр', icon: 'subjects' },
    // Кабинет (`/`) и есть прогресс: уровень, XP, средний балл и отсчёт до ЕНТ.
    { to: '/', label: 'Мой прогресс', short: 'Прогресс', icon: 'progress' },
    { to: '/settings', label: 'Профиль', short: 'Профиль', icon: 'profile' },
  ]
  const extra = [
    { to: '/history', label: 'История', short: 'История', icon: 'history' },
  ]
  if (grade === 11) {
    extra.unshift(
      { to: '/grant-calc', label: 'Гранты ЕНТ', short: 'Гранты', icon: 'grant-calc' },
      { to: '/duels', label: 'Дуэли', short: 'Дуэли', icon: 'duels' },
    )
  }
  return [
    { title: '', links: main },
    { title: 'Дополнительно', links: extra },
  ]
}

// Кабинет тренера: 13 пунктов одним списком было не найти нужный. Три группы по
// смыслу — учебный процесс, контент банка, цифры.
const teacherSections = [
  {
    title: 'Обучение',
    links: [
      { to: '/teacher/assign', label: 'Уроки и проверка', short: 'Уроки', icon: 'assign' },
      { to: '/teacher/students', label: 'Ученики и группы', short: 'Ученики', icon: 'students' },
    ],
  },
  {
    title: 'Контент',
    links: [
      { to: '/teacher/book-bank', label: 'Книжный банк RU/KK', short: 'Банк книг', icon: 'book-bank' },
      { to: '/teacher/book-ingest', label: 'Оцифровка', short: 'Оцифровка', icon: 'book-ingest' },
      { to: '/teacher/bank', label: 'База ЕНТ и импорт', short: 'База ЕНТ', icon: 'questions' },
    ],
  },
  {
    title: 'Аналитика',
    links: [
      { to: '/teacher', label: 'Дашборд', short: 'Дашборд', icon: 'teacher-dashboard' },
      { to: '/teacher/tests', label: 'Результаты', short: 'Результаты', icon: 'results' },
      { to: '/teacher/settings', label: 'Настройки', short: 'Настройки', icon: 'admin' },
    ],
  },
]

const flatLinks = (sections) => sections.flatMap(s => s.links)

function NavIcon({ name }) {
  const Icon = iconMap[name]
  return Icon ? <Icon style={iconStyle} /> : null
}

export default function Layout() {
  const { user, logout } = useAuth()
  const { mode, setMode, switchable } = useViewMode()
  const navigate = useNavigate()
  const location = useLocation()

  const isActive = (to) => {
    const path = location.pathname
    // Дашборд живёт ровно на /teacher: иначе он подсвечивался бы на любом
    // /teacher/… и в сайдбаре горели бы два пункта сразу.
    if (to === '/teacher') return path === '/teacher' || path === '/teacher/'
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

  const isTeacherMode = mode === 'teacher'
  const sections = isTeacherMode ? teacherSections : studentSections(user?.grade)
  const links = flatLinks(sections)

  // Переключатель ведёт не только меню, но и экран: один клик — и владелец
  // платформы видит кабинет тренера или страницу уроков глазами ребёнка.
  const switchMode = (next) => {
    if (next === mode) return
    setMode(next)
    navigate(next === 'teacher' ? '/teacher' : '/assignments')
  }

  // Пунктов больше, чем влезает в строку на телефоне, поэтому активный подводим
  // в центр: иначе тренер открывает «Дашборд» и не видит, что он подсвечен.
  const activeTabRef = useRef(null)
  useEffect(() => {
    activeTabRef.current?.scrollIntoView({ inline: 'center', block: 'nearest' })
  }, [location.pathname, isTeacherMode])

  const initials = user?.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.username?.[0]?.toUpperCase() || '?'

  // класс ученика рядом с именем: тренер и сам ученик должны видеть, кто в кабинете
  const roleLabel = [
    user?.role === 'teacher' ? 'Учитель' : user?.role === 'admin' ? 'Админ' : 'Ученик',
    user?.grade ? `${user.grade} класс` : '',
  ].filter(Boolean).join(' · ')

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-logo"><img src="/assets/logo.png" alt="" className="sidebar-logo-img" /></div>
        <nav className="sidebar-nav">
          {sections.map(section => (
            <div key={section.title || 'main'} className="sidebar-section">
              {section.title && <div className="sidebar-section-title">{section.title}</div>}
              {section.links.map(link => (
                <NavLink key={link.to} to={link.to}
                         end={link.to === '/' || link.to === '/teacher'}
                         className={`sidebar-link ${isActive(link.to) ? 'active' : ''}`}>
                  <span className="sidebar-link-icon"><NavIcon name={link.icon} /></span>
                  {link.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="sidebar-avatar" style={{ overflow: 'hidden' }}>{user?.avatar ? <img src={user.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : initials}</div>
            <div>
              <div className="sidebar-username">{user?.full_name || user?.username}</div>
              <div className="sidebar-role">{roleLabel}</div>
            </div>
          </div>
          {switchable && (
            <div className="sidebar-mode-switch">
              {['teacher', 'student'].map(m => (
                <button key={m} type="button"
                        className={`sidebar-mode-btn ${mode === m ? 'is-active' : ''}`}
                        onClick={() => switchMode(m)}>
                  {m === 'teacher' ? '👨‍🏫 Учитель' : '🎒 Ученик'}
                </button>
              ))}
            </div>
          )}
          {user?.is_superuser && (
            // Django-админка — отдельное приложение на `/admin/`, поэтому ссылка
            // настоящая: через React-роуты она бы осталась в этом же окне SPA.
            <a className="sidebar-admin-link" href="/admin/">⚙️ Django Admin</a>
          )}
          <button className="btn btn-outline sidebar-logout" onClick={handleLogout}>
            Выйти
          </button>
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
      {/* Нижняя панель вкладок и пилюля режима — один контейнер: раньше пилюля
          висела поверх панели и перекрывала подписи пунктов. */}
      <div className="mobile-dock">
        <nav className="mobile-tabbar">
          {links.map(link => {
            const active = isActive(link.to)
            return (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === '/' || link.to === '/teacher'}
                ref={active ? activeTabRef : null}
                className={`mobile-tab ${active ? 'active' : ''}`}
              >
                <span className="mobile-tab-icon"><NavIcon name={link.icon} /></span>
                {link.short || link.label}
              </NavLink>
            )
          })}
        </nav>
        {switchable && (
          <div className="mobile-mode-switch">
            {['teacher', 'student'].map(m => (
              <button key={m} type="button"
                      className={`sidebar-mode-btn ${mode === m ? 'is-active' : ''}`}
                      onClick={() => switchMode(m)}>
                {m === 'teacher' ? '👨‍🏫 Учитель' : '🎒 Ученик'}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
