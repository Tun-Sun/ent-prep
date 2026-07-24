import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Trophy, Medal, Target, Users, Search } from 'lucide-react'
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

  const medalIcons = [
    <Trophy key={0} size={18} strokeWidth={1.5} fill="#F6C326" color="#F6C326" />,
    <Medal key={1} size={18} strokeWidth={1.5} fill="#A8A8A8" color="#A8A8A8" />,
    <Medal key={2} size={18} strokeWidth={1.5} fill="#CD7F32" color="#CD7F32" />,
  ]

  return (
    <div className="dashboard" style={{ maxWidth: 700 }}>
      <div
        style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 18px', marginBottom: 16, cursor: 'pointer', borderRadius: 'var(--radius)', transition: 'background 0.2s', background: 'var(--card)', border: '1px solid var(--border)' }}
        onClick={() => navigate(-1)}>
        <ArrowLeft size={18} strokeWidth={1.5} />
        <span style={{ fontSize: 14, fontWeight: 600 }}>Назад</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 28 }}>
        <div style={{ width: 52, height: 52, borderRadius: 18, background: 'linear-gradient(135deg, #F6C326, #F59E0B)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 8px 24px rgba(246, 195, 38, 0.25)' }}>
          <Trophy size={26} strokeWidth={1.5} color="#fff" />
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Кто прошёл больше тестов</div>
          <h1 style={{ fontSize: 30, fontWeight: 800, color: 'var(--text)', margin: 0 }}>Таблица лидеров</h1>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 16, background: 'var(--card)', borderRadius: 'var(--radius)', padding: 4, border: '1px solid var(--border)' }}>
        {TABS.map(t => (
          <button key={t}
            onClick={() => setTab(t)}
            style={{
              flex: 1, height: 40, borderRadius: 14, border: 'none', cursor: 'pointer',
              fontSize: 14, fontWeight: 600,
              background: tab === t ? 'var(--primary)' : 'transparent',
              color: tab === t ? '#fff' : 'var(--text-secondary)',
              transition: 'all 0.2s',
            }}>
            {t}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {PERIODS.map(p => (
          <button key={p}
            onClick={() => setPeriod(p)}
            style={{
              flex: 1, height: 40, borderRadius: 12, border: '1.5px solid var(--border)', cursor: 'pointer',
              fontSize: 14, fontWeight: 600,
              background: period === p ? 'var(--primary)' : 'var(--card)',
              color: period === p ? '#fff' : 'var(--text)',
              transition: 'all 0.2s',
            }}>
            {p}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 24, overflowX: 'auto', paddingBottom: 8 }}
        className="leaderboard-pills">
        <button onClick={() => setActiveSubject(null)}
          style={{
            flexShrink: 0, height: 40, borderRadius: 20, border: '1.5px solid var(--border)', cursor: 'pointer',
            padding: '0 20px', fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap',
            background: activeSubject === null ? 'var(--primary)' : 'var(--card)',
            color: activeSubject === null ? '#fff' : 'var(--text)',
            transition: 'all 0.2s',
          }}>
          Все предметы
        </button>
        {subjects.map(s => (
          <button key={s.id} onClick={() => setActiveSubject(s.id)}
            style={{
              flexShrink: 0, height: 40, borderRadius: 20, border: '1.5px solid var(--border)', cursor: 'pointer',
              padding: '0 20px', fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap',
              background: activeSubject === s.id ? 'var(--primary)' : 'var(--card)',
              color: activeSubject === s.id ? '#fff' : 'var(--text)',
              transition: 'all 0.2s',
            }}>
            {s.icon} {s.name}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {users.length === 0 && (
          <div style={{ textAlign: 'center', padding: '56px 24px', background: 'var(--card)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
            <Target size={40} strokeWidth={1.5} style={{ color: 'var(--text-secondary)', marginBottom: 12, opacity: 0.5 }} />
            <p style={{ color: 'var(--text-secondary)', fontSize: 15, fontWeight: 500 }}>Пока никто не прошёл тесты. Будь первым!</p>
          </div>
        )}
        {users.map((u, i) => (
          <div key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 20px', background: 'var(--card)', borderRadius: 'var(--radius)', border: '1px solid var(--border)', transition: 'box-shadow 0.2s', boxShadow: i < 3 ? '0 4px 16px rgba(0,0,0,0.04)' : 'none' }}>
            <div style={{
              width: 40, height: 40, borderRadius: 14,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: i < 3 ? ['rgba(246,195,38,0.15)', 'rgba(168,168,168,0.15)', 'rgba(205,127,50,0.15)'][i] : 'var(--bg)',
              color: i < 3 ? ['#B8860B', '#666', '#8B4513'][i] : 'var(--text-secondary)',
              fontSize: 15, fontWeight: 700, flexShrink: 0,
            }}>
              {i < 3 ? medalIcons[i] : `#${i + 1}`}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>{u.full_name || u.username}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>{u.tests_taken} {u.tests_taken === 1 ? 'тест' : 'тестов'}</div>
            </div>
            <div style={{
              padding: '4px 14px', borderRadius: 100,
              background: 'linear-gradient(135deg, #FF603B, #EF4444)',
              color: '#fff', fontSize: 16, fontWeight: 700, flexShrink: 0,
              boxShadow: '0 3px 10px rgba(255,96,59,0.2)',
            }}>
              {u.avg_score}%
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
