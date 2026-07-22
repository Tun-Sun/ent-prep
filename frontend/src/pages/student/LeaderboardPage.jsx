import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { dashboardAPI, subjectsAPI } from '../../api'

const PERIODS = ['Неделя', 'Месяц', 'Всё время']
const TABS = ['Все', 'Друзья']

export default function LeaderboardPage() {
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [subjects, setSubjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('Все')
  const [period, setPeriod] = useState('Всё время')
  const [activeSubject, setActiveSubject] = useState(null)

  useEffect(() => {
    const periodMap = { 'Неделя': 'week', 'Месяц': 'month', 'Всё время': 'all' }
    Promise.all([
      dashboardAPI.leaderboard({ period: periodMap[period] || 'all', subject_id: activeSubject || undefined }),
      subjectsAPI.minimal(),
    ])
      .then(([usersRes, subjectsRes]) => {
        setUsers(Array.isArray(usersRes.data) ? usersRes.data : [])
        setSubjects(Array.isArray(subjectsRes.data) ? subjectsRes.data : [])
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [period, activeSubject])

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>

  return (
    <div className="dashboard" style={{ maxWidth: 700 }}>
      {/* Back button */}
      <div className="d-card" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 20px', marginBottom: 16, cursor: 'pointer' }}
        onClick={() => navigate(-1)}>
        <span style={{ fontSize: 18, fontWeight: 700 }}>←</span>
        <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Назад</span>
      </div>

      {/* Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <div style={{ width: 56, height: 56, borderRadius: 16, border: '2px solid #1B1B1B', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28, background: '#fff', boxShadow: '0 4px 0 0 #1B1B1B' }}>
          🏆
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Кто прошёл больше тестов</div>
          <h1 style={{ fontSize: 32, fontWeight: 800, color: 'var(--text)', margin: 0 }}>Таблица лидеров</h1>
        </div>
      </div>

      {/* Tab filter: Все / Друзья */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
        {TABS.map(t => (
          <button key={t}
            onClick={() => setTab(t)}
            style={{
              flex: 1, height: 48, borderRadius: 16, border: '2px solid #1B1B1B', cursor: 'pointer',
              fontSize: 17, fontWeight: 700,
              background: tab === t ? '#111' : '#fff',
              color: tab === t ? '#fff' : 'var(--text)',
              boxShadow: tab === t ? 'none' : '0 3px 0 0 #1B1B1B',
              transition: 'all 0.1s',
              borderBottom: tab === t ? '3px solid var(--primary)' : '2px solid #1B1B1B',
            }}>
            {t}
          </button>
        ))}
      </div>

      {/* Period filter */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
        {PERIODS.map(p => (
          <button key={p}
            onClick={() => setPeriod(p)}
            style={{
              flex: 1, height: 48, borderRadius: 14, border: '2px solid #1B1B1B', cursor: 'pointer',
              fontSize: 16, fontWeight: 600,
              background: period === p ? '#111' : '#fff',
              color: period === p ? '#fff' : 'var(--text)',
              boxShadow: period === p ? 'none' : '0 3px 0 0 #1B1B1B',
              transition: 'all 0.1s',
            }}>
            {p}
          </button>
        ))}
      </div>

      {/* Subject pills */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 24, overflowX: 'auto', paddingBottom: 8 }}
        className="leaderboard-pills">
        <button onClick={() => setActiveSubject(null)}
          style={{
            flexShrink: 0, height: 50, borderRadius: 25, border: '2px solid #1B1B1B', cursor: 'pointer',
            padding: '0 22px', fontSize: 15, fontWeight: 600,
            background: activeSubject === null ? '#111' : '#fff',
            color: activeSubject === null ? '#fff' : 'var(--text)',
            boxShadow: activeSubject === null ? 'none' : '0 3px 0 0 #1B1B1B',
          }}>
          Все предметы
        </button>
        {subjects.map(s => (
          <button key={s.id} onClick={() => setActiveSubject(s.id)}
            style={{
              flexShrink: 0, height: 50, borderRadius: 25, border: '2px solid #1B1B1B', cursor: 'pointer',
              padding: '0 22px', fontSize: 15, fontWeight: 600,
              background: activeSubject === s.id ? '#111' : '#fff',
              color: activeSubject === s.id ? '#fff' : 'var(--text)',
              boxShadow: activeSubject === s.id ? 'none' : '0 3px 0 0 #1B1B1B',
            }}>
            {s.icon} {s.name}
          </button>
        ))}
      </div>

      {/* Users list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {users.length === 0 && (
          <div className="d-card d-chart" style={{ textAlign: 'center', padding: 48 }}>
            <p style={{ color: 'var(--text-secondary)' }}>Пока никто не прошёл тесты. Будь первым! 🚀</p>
          </div>
        )}
        {users.map((u, i) => (
          <div key={u.id} className="d-card" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 20px' }}>
            <div style={{
              width: 38, height: 38, borderRadius: 12, border: '2px solid #1B1B1B',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 16, fontWeight: 700,
              background: i < 3 ? ['#FFC84A', '#D4D4D4', '#CD7F32'][i] : '#E5E7EB',
              color: i < 3 ? '#111' : 'var(--text-secondary)',
              flexShrink: 0,
            }}>
              {i === 0 ? '🏆' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i + 1}`}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)' }}>{u.full_name || u.username}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>📝 {u.tests_taken} {u.tests_taken === 1 ? 'тест' : 'тестов'}</div>
            </div>
            <div style={{
              padding: '4px 16px', borderRadius: 100, border: '2px solid #FF603B',
              background: '#FFE6DE', fontSize: 17, fontWeight: 700, color: '#FF603B',
              flexShrink: 0,
            }}>
              {u.avg_score}%
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}