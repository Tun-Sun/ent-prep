import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { testsAPI } from '../../api'
import { ArrowLeft, ChevronRight, BookOpen, CheckCircle2, CalendarDays } from 'lucide-react'

export default function HistoryPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    testsAPI.history()
      .then(res => setSessions(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>

  return (
    <div style={{ maxWidth: 680, margin: '0 auto' }}>
      <div className="card" style={{
        display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 16px', marginBottom: 20,
        cursor: 'pointer',
      }} onClick={() => navigate(-1)}>
        <ArrowLeft size={16} strokeWidth={1.5} />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Назад</span>
      </div>

      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, color: 'var(--text)', margin: 0 }}>История тестов</h1>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 4 }}>
          Все ваши завершённые тесты
        </p>
      </div>

      {sessions.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '40px 24px' }}>
          <BookOpen size={40} strokeWidth={1.5} style={{ color: 'var(--text-secondary)', marginBottom: 12, opacity: 0.3 }} />
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 16 }}>Вы ещё не прошли ни одного теста</p>
          <Link to="/subjects" className="btn btn-primary" style={{ borderRadius: 12, padding: '10px 20px' }}>Выбрать предмет</Link>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {sessions.map(s => {
            const scoreClass = s.score_percent >= 70 ? '#16a34a' : s.score_percent >= 40 ? '#d97706' : '#dc2626'
            return (
              <Link key={s.id} to={`/test/result/${s.id}`}
                style={{
                  display: 'flex', alignItems: 'center', gap: 14, padding: '16px 20px',
                  background: 'var(--card)', borderRadius: 'var(--radius)',
                  boxShadow: 'var(--shadow)', border: '1px solid var(--border)',
                  textDecoration: 'none', transition: 'all 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--primary-light)'}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
              >
                <div style={{
                  width: 42, height: 42, borderRadius: 12, flexShrink: 0,
                  background: `linear-gradient(135deg, ${scoreClass}15, ${scoreClass}30)`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 22,
                }}>
                  {s.subject_icon || <BookOpen size={20} strokeWidth={1.5} style={{ color: scoreClass }} />}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', marginBottom: 2 }}>
                    {s.subject_name}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <CalendarDays size={12} strokeWidth={1.5} />
                      {new Date(s.completed_at).toLocaleDateString('ru-RU')}
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <CheckCircle2 size={12} strokeWidth={1.5} style={{ color: '#16a34a' }} />
                      {s.correct_answers}/{s.total_questions}
                    </span>
                  </div>
                </div>
                <div style={{
                  fontSize: 20, fontWeight: 800, color: scoreClass, flexShrink: 0,
                  letterSpacing: '-1px',
                }}>
                  {s.score_percent}<span style={{ fontSize: 12, fontWeight: 600, opacity: 0.6 }}>%</span>
                </div>
                <ChevronRight size={16} strokeWidth={1.5} style={{ color: 'var(--text-secondary)', opacity: 0.3, flexShrink: 0 }} />
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
