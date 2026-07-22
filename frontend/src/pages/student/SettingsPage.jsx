import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { authAPI, subjectsAPI } from '../../api'
import { useAuth } from '../../context/AuthContext'

export default function SettingsPage() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [allSubjects, setAllSubjects] = useState([])
  const [selectedSubjects, setSelectedSubjects] = useState([])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([
      authAPI.profile(),
      subjectsAPI.list(),
    ]).then(([prof, subs]) => {
      setProfile(prof.data)
      setAllSubjects(Array.isArray(subs.data) ? subs.data : [])
      setSelectedSubjects(prof.data.profile_subjects || [])
    }).catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const toggleSubject = (id) => {
    setSelectedSubjects(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const saveSubjects = async () => {
    setSaving(true)
    try {
      await authAPI.updateProfileSubjects(selectedSubjects)
      setProfile(prev => ({ ...prev, profile_subjects: selectedSubjects }))
    } catch {
      alert('Ошибка сохранения')
    }
    setSaving(false)
  }

  const initials = user?.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.username?.[0]?.toUpperCase() || '?'

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>

  const stats = profile?.stats || {}
  const isStudent = user?.role === 'student'

  return (
    <div className="dashboard">
      <div className="d-card" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 20px', marginBottom: 16, cursor: 'pointer' }}
        onClick={() => navigate(-1)}>
        <span style={{ fontSize: 18, fontWeight: 700 }}>←</span>
        <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Назад</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 28 }}>
        <div style={{ width: 48, height: 48, borderRadius: 16, background: '#111', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, border: '2px solid #1B1B1B', boxShadow: '0 3px 0 0 var(--primary)' }}>
          ⚙️
        </div>
        <h1 style={{ fontSize: 36, fontWeight: 800, color: 'var(--text)', margin: 0 }}>Настройки</h1>
      </div>

      <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
        <span>👤</span> Аккаунт
      </div>

      <div className="d-card" style={{ padding: 24, marginBottom: 32 }}>
        <div className="d-card" style={{ display: 'flex', alignItems: 'center', gap: 20, padding: 24, marginBottom: 20 }}>
          <div style={{ position: 'relative' }}>
            <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'var(--primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28, fontWeight: 800, border: '3px solid var(--primary)', outline: '3px solid #FFC84A', outlineOffset: 2 }}>
              {initials}
            </div>
            <div style={{ position: 'absolute', bottom: 0, right: -2, width: 24, height: 24, borderRadius: '50%', background: '#FF603B', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, border: '2px solid #fff', cursor: 'pointer' }}>
              📷
            </div>
          </div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text)' }}>{profile?.full_name || profile?.username}</div>
            <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 4 }}>☁ Синхронизация вкл.</div>
          </div>
        </div>

        <button onClick={handleLogout}
          style={{
            width: '100%', height: 46, borderRadius: 20, border: '1.5px solid #FF5A4E',
            background: '#FFF1F1', cursor: 'pointer', display: 'flex', alignItems: 'center',
            justifyContent: 'center', gap: 8, fontSize: 15, fontWeight: 600, color: '#FF5A4E',
            marginBottom: 20,
          }}>
          ↩ Выйти из аккаунта
        </button>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ color: 'var(--text-secondary)', fontSize: 14 }}>@</span>
              <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Никнейм</span>
            </div>
            <div style={{ fontSize: 14, fontWeight: 600, color: '#FF603B', marginTop: 2 }}>@{profile?.username || 'user'}</div>
            <div style={{ fontSize: 12, color: '#FFC84A', fontWeight: 600 }}>Выберите никнейм</div>
          </div>
          <button style={{ fontSize: 13, fontWeight: 600, color: '#FF603B', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
            Изменить
          </button>
        </div>
      </div>

      {isStudent && (
        <>
          <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>📚</span> Мои предметы
          </div>
          <div className="d-card" style={{ padding: 24, marginBottom: 32 }}>
            <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 16 }}>
              Предметы назначены учителем. Для изменения обратитесь к преподавателю.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {allSubjects.filter(s => selectedSubjects.includes(s.id) || s.subject_type === 'mandatory').map(s => (
                <span key={s.id} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '8px 14px', borderRadius: 10, fontSize: 14, fontWeight: 500,
                  background: s.subject_type === 'mandatory' ? '#FEF3C7' : '#EEF2FF',
                  color: s.subject_type === 'mandatory' ? '#92400E' : '#4338CA',
                  border: '1px solid ' + (s.subject_type === 'mandatory' ? '#FDE68A' : '#C7D2FE'),
                }}>
                  <span>{s.icon}</span>
                  {s.name}
                  {s.subject_type === 'mandatory' && <span style={{ fontSize: 11, opacity: 0.7 }}>обяз.</span>}
                </span>
              ))}
            </div>
          </div>
        </>
      )}

      <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
        <span>🗄</span> Данные
      </div>

      <div className="d-card" style={{ padding: 24, marginBottom: 32 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <span style={{ fontSize: 20 }}>📊</span>
          <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)' }}>Статистика</span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {[
            { label: 'Тестов пройдено', value: stats.total_tests ?? 0 },
            { label: 'Вопросов решено', value: stats.total_questions ?? 0 },
            { label: 'Правильных ответов', value: stats.correct_answers ?? 0 },
            { label: 'Процент верных', value: (stats.avg_score ?? 0) + '%' },
          ].map(row => (
            <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 15, color: 'var(--text-secondary)' }}>{row.label}</span>
              <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)' }}>{row.value}</span>
            </div>
          ))}
        </div>

        <div style={{ height: 1, background: '#E5E7EB', margin: '20px 0' }} />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#FF5A4E', cursor: 'pointer', padding: '4px 0' }}>
            <span>🗑</span>
            <span style={{ fontSize: 15, fontWeight: 600 }}>Удалить всю историю?</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#FF5A4E', cursor: 'pointer', padding: '4px 0' }}>
            <span>🗑</span>
            <span style={{ fontSize: 15, fontWeight: 600 }}>Удалить аккаунт</span>
          </div>
        </div>
      </div>
    </div>
  )
}