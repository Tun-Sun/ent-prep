import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { subjectsAPI, dashboardAPI, authAPI } from '../../api'
import { useAuth } from '../../context/AuthContext'

const SUBJECT_COLORS = [
  '#4F46E5', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
  '#EC4899', '#14B8A6', '#F97316', '#06B6D4', '#84CC16',
  '#6366F1', '#D946EF', '#0EA5E9',
]

export default function SubjectListPage() {
  const { user } = useAuth()
  const [subjects, setSubjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [showEntModal, setShowEntModal] = useState(false)
  const [profile1, setProfile1] = useState('')
  const [profile2, setProfile2] = useState('')
  const [pressedId, setPressedId] = useState(null)
  const [dashboardFilter, setDashboardFilter] = useState(false)
  const [dashboardSubjectIds, setDashboardSubjectIds] = useState([])
  const [profileSubjectIds, setProfileSubjectIds] = useState([])
  const navigate = useNavigate()
  const isTeacher = user?.role === 'teacher' || user?.role === 'admin'

  useEffect(() => {
    subjectsAPI.list()
      .then(res => setSubjects(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
    if (isTeacher) {
      dashboardAPI.dashboardSubjects()
        .then(res => {
          const all = Array.isArray(res.data) ? res.data : []
          setDashboardSubjectIds(all.filter(s => s.selected).map(s => s.id))
        })
        .catch(() => {})
    } else {
      authAPI.profile().then(res => {
        setProfileSubjectIds(res.data.profile_subjects || [])
      }).catch(() => {})
    }
  }, [isTeacher])

  const colorMap = useMemo(() => {
    const m = {}
    subjects.forEach((s, i) => { m[s.id] = SUBJECT_COLORS[i % SUBJECT_COLORS.length] })
    return m
  }, [subjects])

  const profileSubjects = useMemo(
    () => subjects.filter(s => s.subject_type === 'profile' && s.show_in_profiles !== false),
    [subjects]
  )

  const filtered = useMemo(() => {
    if (isTeacher) {
      if (!dashboardFilter || dashboardSubjectIds.length === 0) return subjects
      return subjects.filter(s => dashboardSubjectIds.includes(s.id))
    }
    // Студент — показываем только выбранные + обязательные
    if (profileSubjectIds.length > 0) {
      return subjects.filter(s => s.subject_type === 'mandatory' || profileSubjectIds.includes(s.id))
    }
    return subjects
  }, [subjects, dashboardFilter, dashboardSubjectIds, profileSubjectIds, isTeacher])

  const mandatory = useMemo(
    () => filtered.filter(s => s.subject_type === 'mandatory'),
    [filtered]
  )

  const profile = useMemo(
    () => filtered.filter(s => s.subject_type === 'profile'),
    [filtered]
  )

  const startEnt = () => {
    if (!profile1 || !profile2) return
    if (profile1 === profile2) {
      alert('Профильные предметы должны быть разными')
      return
    }
    navigate('/test/ent', {
      state: { profile1Id: parseInt(profile1), profile2Id: parseInt(profile2) }
    })
  }

  const goToSubject = (subj) => {
    setPressedId(null)
    if (isTeacher) {
      navigate(`/teacher/questions?subject=${subj.id}`)
    } else {
      navigate(`/test/start/${subj.id}`)
    }
  }

  const SubjectRow = ({ subj }) => {
    const color = colorMap[subj.id] || 'var(--primary)'
    const isPressed = pressedId === subj.id
    return (
      <button
        className="subject-row"
        style={{
          '--subject-color': color,
          boxShadow: isPressed ? `0 1px 0 0 var(--border)` : `0 3px 0 0 var(--border)`,
          transform: isPressed ? 'translateY(2px)' : 'none',
        }}
        onMouseDown={() => setPressedId(subj.id)}
        onMouseUp={() => goToSubject(subj)}
        onMouseLeave={() => setPressedId(null)}
        onTouchStart={() => setPressedId(subj.id)}
        onTouchEnd={() => goToSubject(subj)}
      >
        <div className="subject-row-border" style={{ background: color }} />
        <span className="subject-row-icon">{subj.icon}</span>
        <div className="subject-row-info">
          <div className="subject-row-name">{subj.name}</div>
          <div className="subject-row-meta">{subj.total_questions} вопросов · {subj.topic_count} тем · {Math.round(subj.time_limit / 60)} мин</div>
        </div>
        <div className="subject-row-arrow">→</div>
      </button>
    )
  }

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>

  return (
    <div className="subj-page">
      <div className="d-card" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 20px', marginBottom: 16, cursor: 'pointer' }}
        onClick={() => navigate(-1)}>
        <span style={{ fontSize: 18, fontWeight: 700 }}>←</span>
        <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Назад</span>
      </div>
      <div className="subj-header">
        <div className="subj-eyebrow">Банк вопросов</div>
        <h1 className="subj-title">Предметы</h1>
        <p className="subj-subtitle">Выберите предмет для тренировки или начните полную симуляцию ЕНТ</p>
      </div>

      {isTeacher && dashboardSubjectIds.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <button onClick={() => setDashboardFilter(v => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 14, fontWeight: 600,
              padding: '8px 18px', borderRadius: 12, border: '2px solid #1B1B1B',
              background: dashboardFilter ? '#111' : '#fff',
              color: dashboardFilter ? '#fff' : 'var(--text)',
              boxShadow: dashboardFilter ? 'none' : '0 2px 0 0 #1B1B1B',
            }}>
            {dashboardFilter ? '✓' : '○'} Только выбранные
          </button>
        </div>
      )}

      <button className="ent-banner" onClick={() => setShowEntModal(true)}>
        <div className="ent-banner-border" />
        <span className="ent-banner-icon">🎯</span>
        <div className="ent-banner-text">
          <div className="ent-banner-title">Полная симуляция ЕНТ</div>
          <div className="ent-banner-desc">120 вопросов · 5 предметов · 240 минут</div>
        </div>
        <span className="ent-banner-badge">Начать</span>
      </button>

      {mandatory.length > 0 && (
        <div className="subj-section">
          <div className="subj-section-label">Обязательные предметы</div>
          <div className="subj-section-list">
            {mandatory.map(s => <SubjectRow key={s.id} subj={s} />)}
          </div>
        </div>
      )}

      {profile.length > 0 && (
        <div className="subj-section">
          <div className="subj-section-label">Профильные предметы</div>
          <div className="subj-section-list">
            {profile.map(s => <SubjectRow key={s.id} subj={s} />)}
          </div>
        </div>
      )}

      {showEntModal && (
        <div className="modal-overlay" onClick={() => setShowEntModal(false)}>
          <div className="modal modal-ent" onClick={e => e.stopPropagation()}>
            <h2>Начать ЕНТ тест</h2>
            <p>Выберите два профильных предмета для полной симуляции:</p>
            <div className="ent-modal-info">
              <div className="ent-modal-info-item"><strong>История Казахстана</strong> — 20 вопросов</div>
              <div className="ent-modal-info-item"><strong>Грамотность чтения</strong> — 10 вопросов</div>
              <div className="ent-modal-info-item"><strong>Математическая грамотность</strong> — 10 вопросов</div>
              <div className="ent-modal-info-item" style={{ color: 'var(--primary)', fontWeight: 600 }}>+ 2 профильных предмета по 40 вопросов</div>
            </div>
            <div className="ent-modal-selects">
              <select value={profile1} onChange={e => setProfile1(e.target.value)} className="form-select">
                <option value="">Профильный предмет 1</option>
                {profileSubjects.map(s => (
                  <option key={s.id} value={s.id} disabled={s.id === profile2}>{s.icon} {s.name}</option>
                ))}
              </select>
              <select value={profile2} onChange={e => setProfile2(e.target.value)} className="form-select">
                <option value="">Профильный предмет 2</option>
                {profileSubjects.map(s => (
                  <option key={s.id} value={s.id} disabled={s.id === profile1}>{s.icon} {s.name}</option>
                ))}
              </select>
            </div>
            <div className="ent-modal-actions">
              <button className="btn btn-outline" onClick={() => setShowEntModal(false)}>Отмена</button>
              <button className="btn btn-success" onClick={startEnt} disabled={!profile1 || !profile2 || profile1 === profile2}>
                Начать тест
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
