import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer
} from 'recharts'
import { Settings, X, ExternalLink, Users, Trophy, Medal, GraduationCap, BookOpen,
         CheckCircle2, Inbox, Link2, Library, ClipboardList } from 'lucide-react'
import { dashboardAPI, subjectsAPI, testsAPI } from '../../api'

const COLORS = ['#4F46E5', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6', '#F97316']

// «1 ответов ждут» глаз цепляет сразу: русская форма числительного считается по правилам
const plural = (n, one, few, many) => {
  const m10 = n % 10, m100 = n % 100
  if (m10 === 1 && m100 !== 11) return one
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few
  return many
}

// Ссылка урока та же, что на экране конструктора: макросы в фигурных скобках
// подставит GetCourse при показе. Без `GC_SSO_SECRET` сервер подпись урока не даёт,
// и ссылка заведомо отклоняется — кнопка честно гаснет, а не копирует нерабочий URL.
function LessonLinkButton({ lesson }) {
  const [copied, setCopied] = useState('')
  const token = lesson.lesson_token || ''
  const link = `${window.location.origin}/api/lesson/join/` +
    `?assignment_id=${lesson.id}&lesson_token=${token}` +
    `&gc_uid={uid}&email={email}&first_name={first_name}&last_name={last_name}`

  const copy = () => {
    navigator.clipboard?.writeText(link).then(() => setCopied('ok'), () => setCopied('manual'))
    setTimeout(() => setCopied(''), 2500)
  }

  return (
    <button className="btn btn-sm btn-outline" onClick={copy} disabled={!token}
            style={{ borderRadius: 10 }}
            title={token ? link
                         : 'На сервере не задан GC_SSO_SECRET — без подписи урока ссылка не работает'}>
      <Link2 size={13} strokeWidth={1.5} style={{ verticalAlign: -2, marginRight: 5 }} />
      {copied === 'ok' ? 'Ссылка скопирована'
       : copied === 'manual' ? 'Скопируйте вручную'
       : 'Скопировать ссылку урока'}
    </button>
  )
}

export default function TeacherDashboardPage() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showSettings, setShowSettings] = useState(false)
  const [allSubjects, setAllSubjects] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [saving, setSaving] = useState(false)
  const [detailSubject, setDetailSubject] = useState(null)
  const [sessions, setSessions] = useState([])
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [topPeriod, setTopPeriod] = useState('Всё время')
  const [topSubject, setTopSubject] = useState(null)
  const [topSubjects, setTopSubjects] = useState([])

  const load = () => {
    setLoading(true)
    const periodMap = { 'Неделя': 'week', 'Месяц': 'month', 'Всё время': 'all' }
    const params = { period: periodMap[topPeriod] || 'all' }
    if (topSubject) { params.subject_id = topSubject }
    dashboardAPI.teacher(params)
      .then(res => {
        setData(res.data)
        if (res.data.dashboard_subject_ids) {
          setSelectedIds(res.data.dashboard_subject_ids)
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [topPeriod, topSubject])

  useEffect(() => {
    dashboardAPI.dashboardSubjects().then(res => {
      const all = Array.isArray(res.data) ? res.data : []
      setTopSubjects(all.filter(s => s.selected))
    }).catch(() => {})
  }, [])

  const openSettings = () => {
    subjectsAPI.minimal().then(res => {
      setAllSubjects(Array.isArray(res.data) ? res.data : [])
    }).catch(() => {})
    setShowSettings(true)
  }

  const toggleSubject = (id) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const saveSubjects = async () => {
    setSaving(true)
    try {
      await dashboardAPI.updateDashboardSubjects(selectedIds)
      setShowSettings(false)
      load()
    } catch { alert('Ошибка сохранения') }
    finally { setSaving(false) }
  }

  const openDetail = (subjectId, subjectName) => {
    setDetailSubject(subjectName)
    setSessionsLoading(true)
    testsAPI.teacherHistory({ subject: subjectId })
      .then(res => setSessions(Array.isArray(res.data) ? res.data : []))
      .catch(() => {})
      .finally(() => setSessionsLoading(false))
  }

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (!data) return <div className="alert alert-error">Не удалось загрузить данные</div>

  const pieData = (data.subject_stats || []).map((s, i) => ({
    id: s.id,
    name: s.name,
    value: s.test_count,
    avg: s.avg_score,
    lessons: s.lesson_count || 0,
    bank: s.bank_count || 0,
    color: COLORS[i % COLORS.length],
  }))

  const maxCount = Math.max(...pieData.map(d => d.value), 1)

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Дашборд учителя</h1>
          <p className="page-subtitle">Обзор прогресса учеников</p>
        </div>
        <button className="btn btn-outline" onClick={openSettings}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 12 }}>
          <Settings size={16} strokeWidth={1.5} />
          Предметы
        </button>
      </div>

      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 420, borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: 18, fontWeight: 600 }}>Предметы на дашборде</h3>
              <button className="btn btn-sm" onClick={() => setShowSettings(false)}
                style={{ borderRadius: 8, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X size={16} />
              </button>
            </div>
            <div className="modal-body" style={{ maxHeight: 400, overflowY: 'auto', padding: '8px 0' }}>
              {allSubjects.map(s => (
                <label key={s.id} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 20px',
                  cursor: 'pointer', borderRadius: 8, transition: 'background 0.1s',
                }}>
                  <input type="checkbox" checked={selectedIds.includes(s.id)}
                    onChange={() => toggleSubject(s.id)}
                    style={{ width: 18, height: 18, cursor: 'pointer', accentColor: 'var(--primary)' }} />
                  <span style={{ fontSize: 16 }}>{s.icon}</span>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{s.name}</span>
                </label>
              ))}
              {allSubjects.length === 0 && <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: 24 }}>Загрузка...</p>}
            </div>
            <div className="modal-footer" style={{ borderTop: '1px solid var(--border)', padding: '16px 20px', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-outline" onClick={() => setShowSettings(false)}
                style={{ borderRadius: 12, padding: '8px 18px' }}>Отмена</button>
              <button className="btn btn-primary" onClick={saveSubjects} disabled={saving}
                style={{ borderRadius: 12, padding: '8px 18px', opacity: saving ? 0.6 : 1 }}>
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Четыре метрики сверху. «Ждут проверки» — кликабельная: с дашборда тренер
          идёт доводить ответы, а не смотреть на цифру. */}
      <div className="stats-grid">
        <div className="stat-card">
          <ClipboardList size={22} strokeWidth={1.5} style={{ color: 'var(--primary)', marginBottom: 6 }} />
          <div className="stat-value">{data.active_lesson_count || 0}</div>
          <div className="stat-label">Активных уроков</div>
        </div>
        <button type="button" className={`stat-card stat-card-clickable${data.pending_review ? ' is-alert' : ''}`}
                onClick={() => navigate('/teacher/assign')}>
          <Inbox size={22} strokeWidth={1.5} style={{ color: data.pending_review ? '#B45309' : '#10B981', marginBottom: 6 }} />
          <div className="stat-value">{data.pending_review || 0}</div>
          <div className="stat-label">Ждут проверки</div>
          <div className="stat-meta">
            {data.pending_review
              ? `${data.pending_review} ${plural(data.pending_review, 'ответ ждёт', 'ответа ждут', 'ответов ждут')} вердикта →`
              : 'Очередь ручных вердиктов пуста'}
          </div>
        </button>
        <div className="stat-card">
          <Users size={22} strokeWidth={1.5} style={{ color: '#10B981', marginBottom: 6 }} />
          <div className="stat-value">{data.total_students}</div>
          <div className="stat-label">Учеников</div>
        </div>
        <div className="stat-card">
          <Library size={22} strokeWidth={1.5} style={{ color: '#8B5CF6', marginBottom: 6 }} />
          <div className="stat-value">{(data.book_bank?.ru || 0) + (data.book_bank?.kk || 0)}</div>
          <div className="stat-label">Задач в книжном банке</div>
          <div className="stat-meta">RU {data.book_bank?.ru || 0} · KK {data.book_bank?.kk || 0}</div>
        </div>
      </div>

      <div className="card" style={{ padding: 20, marginBottom: 24 }}>
        <div className="card-header">
          <BookOpen size={16} strokeWidth={1.5} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
          Активные уроки и сдача блоков
        </div>
        {(data.active_lessons || []).length === 0 && (
          <div style={{ padding: '8px 0 16px' }}>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
              Активных уроков нет: соберите первый из книжного банка или базы ЕНТ.
            </div>
            <button className="btn btn-primary" style={{ borderRadius: 10 }}
                    onClick={() => navigate('/teacher/assign')}>
              Собрать урок
            </button>
          </div>
        )}
        {data.active_lessons?.map(l => (
          <div key={l.id} className="lesson-row">
            <div style={{ flex: 1, minWidth: 200 }}>
              <div style={{ fontSize: 15, fontWeight: 600 }}>{l.title}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
                {l.subject_name}
                {l.due_at ? ` · срок до ${String(l.due_at).slice(0, 10)}` : ''}
              </div>
            </div>
            <div style={{ minWidth: 130 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: l.submitted_count ? '#065F46' : 'var(--text-secondary)' }}>
                Сдали: {l.submitted_count} из {l.assigned_count}
              </div>
              <div className="d-subj-bar" style={{ marginTop: 6 }}>
                <div className={`d-subj-bar-fill ${l.assigned_count && l.submitted_count === l.assigned_count ? 'gold' : 'blue'}`}
                     style={{ width: `${l.assigned_count ? Math.max(l.submitted_count / l.assigned_count * 100, 2) : 2}%` }} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn btn-sm btn-secondary" style={{ borderRadius: 10 }}
                      onClick={() => navigate(`/teacher/assign?open=${l.id}`)}>
                Матрица результатов
              </button>
              <LessonLinkButton lesson={l} />
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
        <div className="card" style={{ padding: 20 }}>
          <div className="card-header">Средний балл по предметам</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data.subject_stats || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis dataKey="name" stroke="#94A3B8" fontSize={12} tick={{ fill: '#94A3B8' }} />
              <YAxis domain={[0, 100]} stroke="#94A3B8" fontSize={12} tick={{ fill: '#94A3B8' }} />
              <Tooltip
                contentStyle={{ borderRadius: 12, border: '1px solid var(--border)', boxShadow: 'var(--shadow)' }}
                formatter={(value) => [`${value}%`, 'Средний балл']} />
              <Bar dataKey="avg_score" fill="#4F46E5" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card" style={{ padding: 20 }}>
          <div className="card-header">Предметы в работе</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {pieData.map((item, i) => (
              <div key={item.name}
                onClick={() => item.value > 0 && openDetail(item.id, item.name)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, cursor: item.value > 0 ? 'pointer' : 'default',
                  padding: '4px 0',
                }}>
                <div style={{ width: 12, height: 12, borderRadius: 4, background: item.color, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600 }}>{item.name}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{item.value} {plural(item.value, 'тест', 'теста', 'тестов')}</span>
                  </div>
                  <div style={{ height: 6, background: '#E2E8F0', borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', borderRadius: 4, background: item.color,
                      width: `${(item.value / maxCount) * 100}%`, minWidth: item.value > 0 ? 4 : 0,
                    }} />
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
                    Уроков: {item.lessons} · Банк: {item.bank}
                  </div>
                </div>
              </div>
            ))}
            {pieData.length === 0 && (
              <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 24 }}>
                Предметов в работе пока нет: они появятся, когда в них будет урок, банк задач или сданные тесты
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '20px 24px 0' }}>
          <div className="card-header">
            <Trophy size={16} strokeWidth={1.5} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
            Топ учеников
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            {['Неделя', 'Месяц', 'Всё время'].map(p => {
              const active = topPeriod === p
              return (
                <button key={p} onClick={() => setTopPeriod(p)}
                  style={{
                    padding: '6px 16px', borderRadius: 100, border: 'none', cursor: 'pointer',
                    fontSize: 13, fontWeight: 600,
                    background: active ? 'var(--primary)' : '#F1F5F9',
                    color: active ? '#fff' : 'var(--text)',
                  }}>
                  {p}
                </button>
              )
            })}
          </div>
          <div style={{ display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 4, marginBottom: 4 }}>
            <button onClick={() => setTopSubject(null)}
              style={{
                flexShrink: 0, height: 34, borderRadius: 100, border: 'none', cursor: 'pointer',
                padding: '0 16px', fontSize: 13, fontWeight: 600,
                background: topSubject === null ? 'var(--primary)' : '#F1F5F9',
                color: topSubject === null ? '#fff' : 'var(--text)',
              }}>
              Все предметы
            </button>
            {topSubjects.map(s => {
              const active = topSubject === s.id
              return (
                <button key={s.id} onClick={() => setTopSubject(s.id)}
                  style={{
                    flexShrink: 0, height: 34, borderRadius: 100, border: 'none', cursor: 'pointer',
                    padding: '0 16px', fontSize: 13, fontWeight: 600,
                    background: active ? 'var(--primary)' : '#F1F5F9',
                    color: active ? '#fff' : 'var(--text)',
                  }}>
                  {s.icon} {s.name}
                </button>
              )
            })}
          </div>
        </div>
        {data.top_students && data.top_students.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  <th style={{ textAlign: 'left', padding: '12px 24px', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Место</th>
                  <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Ученик</th>
                  <th style={{ textAlign: 'center', padding: '12px 8px', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Средний балл</th>
                  <th style={{ textAlign: 'center', padding: '12px 24px', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Тестов</th>
                </tr>
              </thead>
              <tbody>
                {data.top_students.map((s, i) => (
                  <tr key={s.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '14px 24px' }}>
                      <div style={{
                        width: 32, height: 32, borderRadius: 8,
                        background: i < 3 ? 'rgba(245,158,11,0.1)' : 'rgba(0,0,0,0.03)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontWeight: 700, fontSize: 14, color: i < 3 ? '#B45309' : 'var(--text-secondary)',
                      }}>
                        {i === 0 ? <Medal size={16} strokeWidth={2} style={{ color: '#F59E0B' }} /> :
                         i === 1 ? <Medal size={16} strokeWidth={2} style={{ color: '#9CA3AF' }} /> :
                         i === 2 ? <Medal size={16} strokeWidth={2} style={{ color: '#D97706' }} /> :
                         i + 1}
                      </div>
                    </td>
                    <td style={{ padding: '14px 8px', fontWeight: 600, fontSize: 14 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <GraduationCap size={16} strokeWidth={1.5} style={{ color: 'var(--text-secondary)', flexShrink: 0 }} />
                        {s.full_name || s.username}
                      </div>
                    </td>
                    <td style={{ textAlign: 'center', padding: '14px 8px' }}>
                      <span style={{
                        padding: '3px 10px', borderRadius: 100, fontSize: 13, fontWeight: 700,
                        background: s.avg_score >= 70 ? 'rgba(16,185,129,0.1)' : s.avg_score >= 40 ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)',
                        color: s.avg_score >= 70 ? '#065F46' : s.avg_score >= 40 ? '#92400E' : '#991B1B',
                      }}>
                        {s.avg_score}%
                      </span>
                    </td>
                    <td style={{ textAlign: 'center', padding: '14px 24px', color: 'var(--text-secondary)', fontSize: 14 }}>
                      <CheckCircle2 size={14} strokeWidth={1.5} style={{ display: 'inline', marginRight: 4, verticalAlign: -1 }} />
                      {s.test_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-secondary)' }}>
            Нет данных за выбранный период
          </div>
        )}
      </div>

      {detailSubject && (
        <div className="modal-overlay" onClick={() => setDetailSubject(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 600, borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: 18, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                <BookOpen size={18} strokeWidth={1.5} />
                {detailSubject} — результаты
              </h3>
              <button className="btn btn-sm" onClick={() => setDetailSubject(null)}
                style={{ borderRadius: 8, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X size={16} />
              </button>
            </div>
            <div className="modal-body" style={{ maxHeight: 400, overflowY: 'auto', padding: '12px 20px' }}>
              {sessionsLoading ? (
                <div className="text-center"><div className="spinner"></div></div>
              ) : sessions.length === 0 ? (
                <p style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 24 }}>Нет результатов</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {sessions.map(s => (
                    <div key={s.id} style={{
                      display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
                      borderRadius: 12, border: '1px solid var(--border)', cursor: 'pointer',
                      transition: 'border-color 0.15s',
                    }}
                      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--primary-light)'}
                      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
                      onClick={() => { navigate(`/teacher/tests/${s.id}`); setDetailSubject(null) }}>
                      <div style={{
                        width: 44, height: 44, borderRadius: 12, flexShrink: 0,
                        background: s.score_percent >= 70 ? 'rgba(16,185,129,0.1)' : s.score_percent >= 40 ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontWeight: 800, fontSize: 16, color: s.score_percent >= 70 ? '#059669' : s.score_percent >= 40 ? '#D97706' : '#DC2626',
                      }}>
                        {s.score_percent}<span style={{ fontSize: 10 }}>%</span>
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: 14 }}>{s.student_name || s.student_username}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                          {s.correct_answers}/{s.total_questions} · {s.completed_at ? new Date(s.completed_at).toLocaleDateString('ru-RU') : ''}
                        </div>
                      </div>
                      <ExternalLink size={16} strokeWidth={1.5} style={{ color: 'var(--text-secondary)', flexShrink: 0, opacity: 0.4 }} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
