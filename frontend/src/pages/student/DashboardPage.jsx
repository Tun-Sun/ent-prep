import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TrendingUp, Trophy, Wallet, Settings, FileText } from 'lucide-react'
import { dashboardAPI } from '../../api'
import { useAuth } from '../../context/AuthContext'

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

  const iconSize = 22
  const menuItems = [
    { icon: <TrendingUp size={iconSize} strokeWidth={1.5} />, color: '#4BC97A', label: 'Прогресс', to: '/progress' },
    { icon: <Trophy size={iconSize} strokeWidth={1.5} />, color: '#FFC84A', label: 'Таблица лидеров', to: '/leaderboard' },
    { icon: <Wallet size={iconSize} strokeWidth={1.5} />, color: '#FF5A4E', label: 'Калькулятор грантов', to: '/grant-calc' },
    { icon: <Settings size={iconSize} strokeWidth={1.5} />, color: '#6E7482', label: 'Настройки', to: '/settings' },
  ]

  const avgScore = data.avg_score || 0
  const testCount = data.total_tests || 0

  if (!isProgress) {
    return (
      <div className="dashboard">
        <div className="d-card d-profile">
          <div className="d-avatar">{initials}</div>
          <div className="d-profile-info">
            <h2>{user?.full_name || user?.username}</h2>
            <div className="d-badge">⚡ ур. 1</div>
            <div className="d-level">Новичок</div>
          </div>
        </div>

        <div className="d-stats">
          <div className="d-card d-stat">
            <div className="d-stat-value">{testCount}</div>
            <div className="d-stat-label">Тестов:</div>
          </div>
          <div className="d-card d-stat">
            <div className="d-stat-value">{avgScore}%</div>
            <div className="d-stat-label">Средний</div>
          </div>
          <div className="d-card d-stat">
            <div className="d-stat-value">{bestScore}%</div>
            <div className="d-stat-label">Лучший</div>
          </div>
        </div>

        <div className="d-menu">
          {menuItems.map(item => (
            <div key={item.label} className="d-card d-menu-card" onClick={() => navigate(item.to)}>
              <div className="d-menu-icon" style={{ background: item.color + '20', borderColor: item.color }}>
                {item.icon}
              </div>
              <div className="d-menu-label">{item.label}</div>
              <div className="d-menu-arrow">›</div>
            </div>
          ))}
        </div>

        {data.subject_progress.length > 0 && (
          <div>
            <div className="d-subj-header">
              <div className="d-subj-title">Предметы</div>
            </div>
            {data.subject_progress.map(subj => (
              <div key={subj.id} className="d-card d-subj-card" onClick={() => navigate(`/test/start/${subj.id}`)}>
                <div className="d-subj-icon">{subj.icon}</div>
                <div className="d-subj-info">
                  <div className="d-subj-name">{subj.name}</div>
                  <div className="d-subj-meta">{subj.tests_taken} тестов · {subj.last_score ? `последний ${subj.last_score}%` : ''}</div>
                  <div className="d-subj-bar">
                    <div className="d-subj-bar-fill" style={{
                      width: `${Math.max(subj.avg_score, 2)}%`,
                      background: subj.avg_score >= 70 ? '#4BC97A' : subj.avg_score >= 40 ? '#FFC84A' : '#FF5A4E'
                    }} />
                  </div>
                </div>
                <div className="d-subj-score">{subj.avg_score}%</div>
              </div>
            ))}
          </div>
        )}

        {data.recent_tests.length > 0 && (
          <div className="d-card d-chart">
            <div className="d-chart-title">Последние результаты</div>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={data.recent_tests}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                <XAxis dataKey="date" stroke="#6E7482" fontSize={12} />
                <YAxis domain={[0, 100]} stroke="#6E7482" fontSize={12} />
                <Tooltip
                  formatter={(value) => [`${value}%`, 'Балл']}
                  labelFormatter={(label) => `Дата: ${label}`}
                />
                <Line type="monotone" dataKey="score" stroke="#FF5E3A" strokeWidth={2} dot={{ r: 4, fill: '#FF5E3A' }} />
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
          <div className="d-stat-value">{testCount}</div>
          <div className="d-stat-label">Тестов сдал</div>
        </div>
        <div className="d-card d-stat">
          <div className="d-stat-value">{avgScore}%</div>
          <div className="d-stat-label">Средний балл</div>
        </div>
        <div className="d-card d-stat">
          <div className="d-stat-value">{bestScore}%</div>
          <div className="d-stat-label">Лучший результат</div>
        </div>
      </div>

      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
          <div style={{ width: 48, height: 48, borderRadius: 14, border: '2px solid #1B1B1B', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fff', boxShadow: '0 4px 0 0 #1B1B1B' }}><Trophy size={24} strokeWidth={1.5} /></div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Кто прошёл больше тестов</div>
            <h2 style={{ fontSize: 24, fontWeight: 800, color: 'var(--text)', margin: 0 }}>Таблица лидеров</h2>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, marginBottom: 20, overflowX: 'auto', paddingBottom: 8 }}>
          <button onClick={() => setLbSubject('all')}
            style={{
              flexShrink: 0, height: 44, borderRadius: 22, border: '2px solid #1B1B1B', cursor: 'pointer',
              padding: '0 20px', fontSize: 14, fontWeight: 600,
              background: lbSubject === 'all' ? '#111' : '#fff',
              color: lbSubject === 'all' ? '#fff' : 'var(--text)',
              boxShadow: lbSubject === 'all' ? 'none' : '0 3px 0 0 #1B1B1B',
            }}>
            Все предметы
          </button>
          {data.subject_progress.map(s => (
            <button key={s.id} onClick={() => setLbSubject(s.id)}
              style={{
                flexShrink: 0, height: 44, borderRadius: 22, border: '2px solid #1B1B1B', cursor: 'pointer',
                padding: '0 20px', fontSize: 14, fontWeight: 600,
                background: lbSubject === s.id ? '#111' : '#fff',
                color: lbSubject === s.id ? '#fff' : 'var(--text)',
                boxShadow: lbSubject === s.id ? 'none' : '0 3px 0 0 #1B1B1B',
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
              <div className="d-card d-chart" style={{ textAlign: 'center', padding: 48 }}>
                <p style={{ color: 'var(--text-secondary)' }}>Пока никто не прошёл тесты. Будь первым! 🚀</p>
              </div>
            )}
            {(leaderboard[lbSubject] || []).slice(0, 10).map((u, i) => (
              <div key={u.id} className="d-card" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px' }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 10, border: '2px solid #1B1B1B',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 15, fontWeight: 700,
                  background: i < 3 ? ['#FFC84A', '#D4D4D4', '#CD7F32'][i] : '#E5E7EB',
                  color: i < 3 ? '#111' : 'var(--text-secondary)',
                  flexShrink: 0,
                }}>
                  {i === 0 ? '🏆' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i + 1}`}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>{u.full_name || u.username}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 4 }}><FileText size={13} strokeWidth={1.5} /> {u.tests_taken} {u.tests_taken === 1 ? 'тест' : 'тестов'}</div>
                </div>
                <div style={{
                  padding: '3px 14px', borderRadius: 100, border: '2px solid #FF603B',
                  background: '#FFE6DE', fontSize: 16, fontWeight: 700, color: '#FF603B',
                  flexShrink: 0,
                }}>
                  {u.avg_score}%
                </div>
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
          {data.subject_progress.map(subj => (
            <div key={subj.id} className="d-card d-subj-card" onClick={() => navigate(`/test/start/${subj.id}`)}>
              <div className="d-subj-icon">{subj.icon}</div>
              <div className="d-subj-info">
                <div className="d-subj-name">{subj.name}</div>
                <div className="d-subj-meta">{subj.tests_taken} тестов · лучший {subj.best_score}%</div>
                <div className="d-subj-bar">
                  <div className="d-subj-bar-fill" style={{
                    width: `${Math.max(subj.avg_score, 2)}%`,
                    background: subj.avg_score >= 70 ? '#4BC97A' : subj.avg_score >= 40 ? '#FFC84A' : '#FF5A4E'
                  }} />
                </div>
              </div>
              <div className="d-subj-score">{subj.avg_score}%</div>
            </div>
          ))}
        </div>
      )}

      {data.recent_tests.length > 0 && (
        <div className="d-card d-chart" style={{ marginTop: 20 }}>
          <div className="d-chart-title">Динамика результатов</div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={data.recent_tests}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="date" stroke="#6E7482" fontSize={12} />
              <YAxis domain={[0, 100]} stroke="#6E7482" fontSize={12} />
              <Tooltip
                formatter={(value) => [`${value}%`, 'Балл']}
                labelFormatter={(label) => `Дата: ${label}`}
              />
              <Line type="monotone" dataKey="score" stroke="#FF5E3A" strokeWidth={2} dot={{ r: 4, fill: '#FF5E3A' }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
