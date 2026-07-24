import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TrendingUp, Trophy, Wallet, Settings, FileText, BookOpen, Zap, Award, Target, Flame, Star } from 'lucide-react'
import { dashboardAPI } from '../../api'
import { useAuth } from '../../context/AuthContext'
import ProgressRing from '../../components/ProgressRing'

const iconSize = 20

const menuItems = [
  { icon: <TrendingUp size={iconSize} strokeWidth={1.5} />, iconClass: 'purple', label: 'Прогресс', sub: 'Последний тест и динамика', to: '/progress' },
  { icon: <Trophy size={iconSize} strokeWidth={1.5} />, iconClass: 'yellow', label: 'Таблица лидеров', sub: 'Соревнуйся с другими', to: '/leaderboard' },
  { icon: <BookOpen size={iconSize} strokeWidth={1.5} />, iconClass: 'green', label: 'Предметы', sub: 'Выбери предмет для теста', to: '/subjects' },
  { icon: <Wallet size={iconSize} strokeWidth={1.5} />, iconClass: 'red', label: 'Калькулятор грантов', sub: 'Узнай свои шансы', to: '/grant-calc' },
  { icon: <Settings size={iconSize} strokeWidth={1.5} />, iconClass: 'gray', label: 'Настройки', sub: 'Аккаунт и уведомления', to: '/settings' },
]

export default function StudentDashboardPage() {
  const { user } = useAuth()
  const location = useLocation()
  const isProgress = location.pathname === '/progress'
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [leaderboard, setLeaderboard] = useState(null)
  const [lbLoading, setLbLoading] = useState(false)
  const [lbSubject, setLbSubject] = useState('all')
  const lbFetched = useRef(false)
  const navigate = useNavigate()

  useEffect(() => {
    dashboardAPI.student()
      .then(res => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!isProgress) return
    if (!data) return
    lbFetched.current = false
  }, [data, isProgress])

  useEffect(() => {
    if (!isProgress) return
    if (!data) return
    if (lbFetched.current) return
    lbFetched.current = true
    setLbLoading(true)
    const subs = data.subject_progress || []
    const ids = subs.map(s => s.id)
    const allPromises = Promise.all([
      dashboardAPI.leaderboard({ period: 'all' }).then(r => ({ id: 'all', data: r.data })),
      ...ids.map(id =>
        dashboardAPI.leaderboard({ subject_id: id, period: 'all' }).then(r => ({ id, data: r.data }))
      ),
    ])
    allPromises
      .then(results => {
        const map = {}
        results.forEach(r => { map[r.id] = r.data })
        setLeaderboard(map)
      })
      .catch(() => {})
      .finally(() => setLbLoading(false))
  }, [isProgress, data])

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (!data) return <div className="alert alert-error">Не удалось загрузить данные</div>

  const initials = user?.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.username?.[0]?.toUpperCase() || '?'
  const bestScore = data.recent_tests.length > 0
    ? Math.max(...data.recent_tests.map(t => t.score))
    : 0
  const avgScore = data.avg_score || 0
  const testCount = data.total_tests || 0

  const xpPercent = Math.min(Math.floor((testCount % 10) / 10 * 100), 100)

  const achievements = [
    { icon: '🏅', label: 'Первая\nсотка', unlocked: bestScore >= 100 },
    { icon: '⭐', label: '5 тестов\nподряд', unlocked: testCount >= 5 },
    { icon: '🔥', label: '7 дней без\nпропусков', unlocked: false },
    { icon: '🎯', label: 'Лучший\nрезультат', unlocked: bestScore >= 90 },
  ]

  if (!isProgress) {
    return (
      <div className="dashboard">
        <div className="d-card d-profile">
          <div className="d-profile-left">
            <div className="d-avatar">{user?.avatar ? <img src={user.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : initials}</div>
            <div className="d-profile-info">
              <h2>{user?.full_name || user?.username}</h2>
              <div className="d-level-row">
                <span className="d-level-dot" />
                <span className="d-level-label">Intellect Level 1</span>
              </div>
              <div className="d-level-name">Новичок</div>
              <div className="d-xp-row">
                <div className="d-xp-bar">
                  <div className="d-xp-fill" style={{ width: `${xpPercent}%` }} />
                </div>
                <span className="d-xp-text">{testCount % 10} / 10 XP</span>
              </div>
            </div>
          </div>
          <ProgressRing percent={avgScore} size={80} strokeWidth={5}>
            <span className="d-ring-value">{avgScore}</span>
            <span className="d-ring-label">средний</span>
          </ProgressRing>
        </div>

        <div className="d-ent-countdown d-card" onClick={() => navigate('/subjects')}>
          <span className="d-countdown-icon">📅</span>
          <div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span className="d-countdown-number">235</span>
              <span className="d-countdown-unit">дней</span>
            </div>
            <div className="d-countdown-label">до ЕНТ — начни подготовку сегодня</div>
          </div>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 20, color: 'var(--text-secondary)', opacity: 0.4 }}>→</span>
        </div>

        <div className="d-stats">
          <div className="d-card d-stat">
            <div className="d-stat-accent yellow" />
            <div className="d-stat-icon">📚</div>
            <div className="d-stat-value">{testCount}</div>
            <div className="d-stat-label">{testCount === 1 ? 'Тест' : 'Тестов'} пройдено</div>
          </div>
          <div className="d-card d-stat">
            <div className="d-stat-accent blue" />
            <div className="d-stat-icon">📈</div>
            <div className="d-stat-value">{avgScore}%</div>
            <div className="d-stat-label">Средний результат</div>
          </div>
          <div className="d-card d-stat">
            <div className="d-stat-accent green" />
            <div className="d-stat-icon">🏆</div>
            <div className="d-stat-value">{bestScore}%</div>
            <div className="d-stat-label">Лучший результат</div>
          </div>
        </div>

        <div className="d-menu">
          {menuItems.map(item => (
            <div key={item.label} className="d-card d-menu-card" onClick={() => navigate(item.to)}>
              <div className={`d-menu-icon ${item.iconClass}`}>
                {item.icon}
              </div>
              <div className="d-menu-content">
                <div className="d-menu-label">{item.label}</div>
                <div className="d-menu-sub">{item.sub}</div>
              </div>
              <span className="d-menu-arrow">→</span>
            </div>
          ))}
        </div>

        <div className="d-achievements">
          {achievements.map((ach, i) => (
            <div key={i} className={`d-card d-achievement ${ach.unlocked ? 'unlocked' : 'locked'}`}>
              <div className="d-achievement-icon">{ach.icon}</div>
              <div className="d-achievement-label">{ach.label.split('\n').map((l, j) => <span key={j}>{l}<br /></span>)}</div>
            </div>
          ))}
        </div>

        {data.subject_progress.length > 0 && (
          <div>
            <div className="d-subj-header">
              <div className="d-subj-title">Мои предметы</div>
            </div>
            {data.subject_progress.map(subj => {
              const barColor = subj.avg_score >= 70 ? 'gold' : subj.avg_score >= 40 ? 'blue' : 'red'
              return (
                <div key={subj.id} className="d-card d-subj-card" onClick={() => navigate(`/test/start/${subj.id}`)}>
                  <div className="d-subj-icon">{subj.icon}</div>
                  <div className="d-subj-info">
                    <div className="d-subj-name">{subj.name}</div>
                    <div className="d-subj-meta">{subj.tests_taken} {subj.tests_taken === 1 ? 'тест' : 'тестов'} · {subj.last_score ? `последний ${subj.last_score}%` : 'ещё нет результатов'}</div>
                    <div className="d-subj-bar">
                      <div className={`d-subj-bar-fill ${barColor}`} style={{ width: `${Math.max(subj.avg_score, 2)}%` }} />
                    </div>
                  </div>
                  <div className="d-subj-score">{subj.avg_score}%</div>
                </div>
              )
            })}
          </div>
        )}

        {data.recent_tests.length > 0 && (
          <div className="d-card d-chart">
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Динамика результатов</div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={data.recent_tests}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.06)" />
                <XAxis dataKey="date" stroke="#6B7280" fontSize={12} />
                <YAxis domain={[0, 100]} stroke="#6B7280" fontSize={12} />
                <Tooltip formatter={(value) => [`${value}%`, 'Балл']} />
                <Line type="monotone" dataKey="score" stroke="#243B82" strokeWidth={2} dot={{ r: 4, fill: '#243B82' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="dashboard">
      <div className="d-stats">
        <div className="d-card d-stat">
          <div className="d-stat-accent yellow" />
          <div className="d-stat-icon">📚</div>
          <div className="d-stat-value">{testCount}</div>
          <div className="d-stat-label">Тестов сдал</div>
        </div>
        <div className="d-card d-stat">
          <div className="d-stat-accent blue" />
          <div className="d-stat-icon">📈</div>
          <div className="d-stat-value">{avgScore}%</div>
          <div className="d-stat-label">Средний балл</div>
        </div>
        <div className="d-card d-stat">
          <div className="d-stat-accent green" />
          <div className="d-stat-icon">🏆</div>
          <div className="d-stat-value">{bestScore}%</div>
          <div className="d-stat-label">Лучший результат</div>
        </div>
      </div>

      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
          <div className="d-menu-icon yellow" style={{ width: 48, height: 48 }}><Trophy size={24} strokeWidth={1.5} /></div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Кто прошёл больше тестов</div>
            <h2 style={{ fontSize: 24, fontWeight: 800, color: 'var(--text)', margin: 0 }}>Таблица лидеров</h2>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, marginBottom: 20, overflowX: 'auto', paddingBottom: 8 }}>
          <button onClick={() => setLbSubject('all')}
            style={{
              flexShrink: 0, height: 40, borderRadius: 20, border: '1px solid var(--border)', cursor: 'pointer',
              padding: '0 18px', fontSize: 13, fontWeight: 600,
              background: lbSubject === 'all' ? 'var(--primary)' : '#fff',
              color: lbSubject === 'all' ? '#fff' : 'var(--text)',
              boxShadow: lbSubject === 'all' ? 'none' : 'var(--shadow)',
            }}>
            Все предметы
          </button>
          {data.subject_progress.map(s => (
            <button key={s.id} onClick={() => setLbSubject(s.id)}
              style={{
                flexShrink: 0, height: 40, borderRadius: 20, border: '1px solid var(--border)', cursor: 'pointer',
                padding: '0 18px', fontSize: 13, fontWeight: 600,
                background: lbSubject === s.id ? 'var(--primary)' : '#fff',
                color: lbSubject === s.id ? '#fff' : 'var(--text)',
                boxShadow: lbSubject === s.id ? 'none' : 'var(--shadow)',
              }}>
              {s.icon} {s.name}
            </button>
          ))}
        </div>
        {lbLoading ? (
          <div className="text-center"><div className="spinner"></div></div>
        ) : leaderboard ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {(!leaderboard[lbSubject] || leaderboard[lbSubject].length === 0) && (
              <div className="card" style={{ textAlign: 'center', padding: 48 }}>
                <p style={{ color: 'var(--text-secondary)' }}>Пока никто не прошёл тесты. Будь первым! 🚀</p>
              </div>
            )}
            {(leaderboard[lbSubject] || []).slice(0, 10).map((u, i) => (
              <div key={u.id} className="card" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px' }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 10,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 15, fontWeight: 700,
                  background: i < 3 ? ['#FEF3C7', '#F3F4F6', '#FDE68A'][i] : '#F3F4F6',
                  color: i < 3 ? '#92400E' : 'var(--text-secondary)',
                  flexShrink: 0,
                }}>
                  {i === 0 ? '🏆' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i + 1}`}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>{u.full_name || u.username}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 4 }}><FileText size={13} strokeWidth={1.5} /> {u.tests_taken} {u.tests_taken === 1 ? 'тест' : 'тестов'}</div>
                </div>
                <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--primary)' }}>{u.avg_score}%</div>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      {data.subject_progress.length > 0 && (
        <div>
          <div className="d-subj-header">
            <div className="d-subj-title">Результаты по предметам</div>
          </div>
          {data.subject_progress.map(subj => {
            const barColor = subj.avg_score >= 70 ? 'gold' : subj.avg_score >= 40 ? 'blue' : 'red'
            return (
              <div key={subj.id} className="card d-subj-card" onClick={() => navigate(`/test/start/${subj.id}`)}>
                <div className="d-subj-icon">{subj.icon}</div>
                <div className="d-subj-info">
                  <div className="d-subj-name">{subj.name}</div>
                  <div className="d-subj-meta">{subj.tests_taken} тестов · лучший {subj.best_score}%</div>
                  <div className="d-subj-bar">
                    <div className={`d-subj-bar-fill ${barColor}`} style={{ width: `${Math.max(subj.avg_score, 2)}%` }} />
                  </div>
                </div>
                <div className="d-subj-score">{subj.avg_score}%</div>
              </div>
            )
          })}
        </div>
      )}

      {data.recent_tests.length > 0 && (
        <div className="card d-chart" style={{ marginTop: 20 }}>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Динамика результатов</div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data.recent_tests}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.06)" />
              <XAxis dataKey="date" stroke="#6B7280" fontSize={12} />
              <YAxis domain={[0, 100]} stroke="#6B7280" fontSize={12} />
              <Tooltip formatter={(value) => [`${value}%`, 'Балл']} />
              <Line type="monotone" dataKey="score" stroke="#243B82" strokeWidth={2} dot={{ r: 4, fill: '#243B82' }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
