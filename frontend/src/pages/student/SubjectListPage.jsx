import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { subjectsAPI, dashboardAPI, authAPI } from '../../api'
import { useAuth } from '../../context/AuthContext'
import { Target, ArrowLeft, ChevronRight, Clock, BookOpen } from 'lucide-react'

export default function SubjectListPage() {
  const { user } = useAuth()
  const [subjects, setSubjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [showEntModal, setShowEntModal] = useState(false)
  const [profile1, setProfile1] = useState('')
  const [profile2, setProfile2] = useState('')
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

  const profileSubjects = useMemo(
    () => subjects.filter(s => s.subject_type === 'profile' && s.show_in_profiles !== false),
    [subjects]
  )

  const filtered = useMemo(() => {
    if (isTeacher) {
      if (!dashboardFilter || dashboardSubjectIds.length === 0) return subjects
      return subjects.filter(s => dashboardSubjectIds.includes(s.id))
    }
    if (profileSubjectIds.length > 0) {
      return subjects.filter(s => s.subject_type === 'mandatory' || profileSubjectIds.includes(s.id))
    }
    return subjects
  }, [subjects, dashboardFilter, dashboardSubjectIds, profileSubjectIds, isTeacher])

  const mandatory = useMemo(() => filtered.filter(s => s.subject_type === 'mandatory'), [filtered])
  const profile = useMemo(() => filtered.filter(s => s.subject_type === 'profile'), [filtered])

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
    if (isTeacher) {
      navigate(`/teacher/questions?subject=${subj.id}`)
    } else {
      navigate(`/test/start/${subj.id}`)
    }
  }

  const SubjectRow = ({ subj }) => {
    const color = subj.color || 'var(--primary)'
    return (
      <div className="card" style={{
        display: 'flex', alignItems: 'center', gap: 16, padding: '16px 20px', marginBottom: 10,
        cursor: 'pointer',
      }} onClick={() => goToSubject(subj)}>
        <div style={{
          width: 44, height: 44, borderRadius: 14,
          background: `linear-gradient(135deg, ${color}22, ${color}44)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 24, flexShrink: 0,
        }}>
          {subj.icon}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="d-subj-name">{subj.name}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <BookOpen size={12} strokeWidth={1.5} /> {subj.total_questions} вопросов
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Clock size={12} strokeWidth={1.5} /> {Math.round(subj.time_limit / 60)} мин
            </span>
          </div>
        </div>
        <ChevronRight size={18} strokeWidth={1.5} style={{ color: 'var(--text-secondary)', opacity: 0.4, flexShrink: 0 }} />
      </div>
    )
  }

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      <div className="card" style={{
        display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 16px', marginBottom: 20,
        cursor: 'pointer',
      }} onClick={() => navigate(-1)}>
        <ArrowLeft size={16} strokeWidth={1.5} />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Назад</span>
      </div>

      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 6 }}>
          Банк вопросов
        </div>
        <h1 style={{ fontSize: 28, fontWeight: 800, color: 'var(--text)', margin: 0 }}>Предметы</h1>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 4 }}>
          Выберите предмет для тренировки или начните полную симуляцию ЕНТ
        </p>
      </div>

      {isTeacher && dashboardSubjectIds.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <button onClick={() => setDashboardFilter(v => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600,
              padding: '8px 16px', borderRadius: 10, border: '1px solid var(--border)',
              background: dashboardFilter ? 'var(--primary)' : '#fff',
              color: dashboardFilter ? '#fff' : 'var(--text)',
              boxShadow: 'var(--shadow)',
            }}>
            {dashboardFilter ? '✓' : '○'} Только выбранные
          </button>
        </div>
      )}

      <div className="d-card d-ent-countdown" style={{ marginBottom: 24 }} onClick={() => setShowEntModal(true)}>
        <Target size={28} strokeWidth={1.5} style={{ color: 'var(--primary)', flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>Полная симуляция ЕНТ</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>120 вопросов · 5 предметов · 240 мин</div>
        </div>
        <span style={{
          padding: '6px 16px', borderRadius: 100, fontSize: 13, fontWeight: 700,
          background: 'var(--primary)', color: '#fff',
        }}>Начать</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 28 }}>
        <div className="card" style={{ padding: '16px 18px', cursor: 'pointer' }} onClick={() => navigate('/test/rush')}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <span style={{ fontSize: 22 }}>⚡</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Question Rush</span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>30 вопросов за 5 минут. Успеешь?</div>
        </div>
        <div className="card" style={{ padding: '16px 18px', cursor: 'pointer' }} onClick={() => navigate('/duels')}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <span style={{ fontSize: 22 }}>⚔️</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Дуэли</span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Вызови одноклассника на битву</div>
        </div>
      </div>

      {mandatory.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <div style={{
            fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
            color: 'var(--text-secondary)', marginBottom: 10, paddingLeft: 4,
          }}>
            Обязательные предметы
          </div>
          {mandatory.map(s => <SubjectRow key={s.id} subj={s} />)}
        </div>
      )}

      {profile.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <div style={{
            fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
            color: 'var(--text-secondary)', marginBottom: 10, paddingLeft: 4,
          }}>
            Профильные предметы
          </div>
          {profile.map(s => <SubjectRow key={s.id} subj={s} />)}
        </div>
      )}

      {showEntModal && (
        <div className="modal-overlay" onClick={() => setShowEntModal(false)}>
          <div className="modal modal-ent" onClick={e => e.stopPropagation()}
            style={{ borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: 20, fontWeight: 800 }}>Начать ЕНТ тест</h3>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 16 }}>
              Выберите два профильных предмета для полной симуляции:
            </p>
            <div style={{
              background: 'rgba(36,59,130,0.04)', borderRadius: 12, padding: '14px 18px',
              marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 8, fontSize: 14,
            }}>
              <div style={{ display: 'flex', gap: 8 }}><span style={{ color: 'var(--primary)', fontWeight: 700 }}>•</span> <strong>История Казахстана</strong> — 20 вопросов</div>
              <div style={{ display: 'flex', gap: 8 }}><span style={{ color: 'var(--primary)', fontWeight: 700 }}>•</span> <strong>Грамотность чтения</strong> — 10 вопросов</div>
              <div style={{ display: 'flex', gap: 8 }}><span style={{ color: 'var(--primary)', fontWeight: 700 }}>•</span> <strong>Математическая грамотность</strong> — 10 вопросов</div>
              <div style={{ display: 'flex', gap: 8, color: 'var(--primary)', fontWeight: 600 }}><span style={{ fontWeight: 700 }}>+</span> 2 профильных предмета по 40 вопросов</div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
              <select value={profile1} onChange={e => setProfile1(e.target.value)}
                style={{
                  padding: '12px 14px', borderRadius: 12, border: '1px solid var(--border)',
                  fontSize: 14, background: '#fff', cursor: 'pointer',
                }}>
                <option value="">Профильный предмет 1</option>
                {profileSubjects.map(s => (
                  <option key={s.id} value={s.id} disabled={s.id === profile2}>{s.icon} {s.name}</option>
                ))}
              </select>
              <select value={profile2} onChange={e => setProfile2(e.target.value)}
                style={{
                  padding: '12px 14px', borderRadius: 12, border: '1px solid var(--border)',
                  fontSize: 14, background: '#fff', cursor: 'pointer',
                }}>
                <option value="">Профильный предмет 2</option>
                {profileSubjects.map(s => (
                  <option key={s.id} value={s.id} disabled={s.id === profile1}>{s.icon} {s.name}</option>
                ))}
              </select>
            </div>
            <div className="modal-footer" style={{ borderTop: '1px solid var(--border)', paddingTop: 16, marginTop: 0 }}>
              <button className="btn btn-outline" onClick={() => setShowEntModal(false)}
                style={{ borderRadius: 12, padding: '10px 20px' }}>Отмена</button>
              <button className="btn btn-primary" onClick={startEnt} disabled={!profile1 || !profile2 || profile1 === profile2}
                style={{ borderRadius: 12, padding: '10px 20px', opacity: (!profile1 || !profile2 || profile1 === profile2) ? 0.5 : 1 }}>
                Начать тест
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
