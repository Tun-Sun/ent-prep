import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer
} from 'recharts'
import { Settings, X, ExternalLink } from 'lucide-react'
import { dashboardAPI, subjectsAPI, testsAPI } from '../../api'

const COLORS = ['#4F46E5', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#8B5CF6', '#EC4899', '#14B8A6']

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
    color: COLORS[i % COLORS.length],
  }))

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Дашборд учителя</h1>
          <p className="page-subtitle">Обзор прогресса учеников</p>
        </div>
        <button className="btn btn-outline" onClick={openSettings}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px' }}>
          <Settings size={16} strokeWidth={1.5} />
          Предметы
        </button>
      </div>

      {/* Modal for subject selection */}
      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 420 }}>
            <div className="modal-header">
              <h3>Предметы на дашборде</h3>
              <button className="btn btn-sm" onClick={() => setShowSettings(false)}><X size={16} /></button>
            </div>
            <div className="modal-body" style={{ maxHeight: 400, overflowY: 'auto' }}>
              {allSubjects.map(s => (
                <label key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', cursor: 'pointer' }}>
                  <input type="checkbox" checked={selectedIds.includes(s.id)}
                    onChange={() => toggleSubject(s.id)}
                    style={{ width: 18, height: 18, cursor: 'pointer' }} />
                  <span style={{ fontSize: 16 }}>{s.icon}</span>
                  <span style={{ fontWeight: 500 }}>{s.name}</span>
                </label>
              ))}
              {allSubjects.length === 0 && <p style={{ color: 'var(--text-secondary)' }}>Загрузка...</p>}
            </div>
            <div className="modal-footer">
              <button className="btn btn-outline" onClick={() => setShowSettings(false)}>Отмена</button>
              <button className="btn btn-primary" onClick={saveSubjects} disabled={saving}>
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">👥</div>
          <div className="stat-value">{data.total_students}</div>
          <div className="stat-label">Учеников</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">📝</div>
          <div className="stat-value">{data.total_tests}</div>
          <div className="stat-label">Тестов сдано</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">📊</div>
          <div className="stat-value">{data.avg_score}%</div>
          <div className="stat-label">Средний балл</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">🏆</div>
          <div className="stat-value">{data.top_students?.[0]?.avg_score || 0}%</div>
          <div className="stat-label">Лучший ученик</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div className="card">
          <div className="card-header">Средний балл по предметам</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data.subject_stats || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="name" stroke="#6B7280" fontSize={12} />
              <YAxis domain={[0, 100]} stroke="#6B7280" fontSize={12} />
              <Tooltip formatter={(value) => [`${value}%`, 'Средний балл']} />
              <Bar dataKey="avg_score" fill="#4F46E5" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div className="card-header">Тесты по предметам</div>
          <div style={{ padding: '8px 0' }}>
            {pieData.map((item, i) => (
              <div key={item.name}
                onClick={() => item.value > 0 && openDetail(item.id, item.name)}
                style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', cursor: item.value > 0 ? 'pointer' : 'default' }}>
                <div style={{ width: 10, height: 10, borderRadius: 3, background: item.color, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600 }}>{item.name}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{item.value} тестов</span>
                  </div>
                  <div style={{ height: 6, borderRadius: 3, background: '#E5E7EB', overflow: 'hidden' }}>
                    <div style={{ height: '100%', borderRadius: 3, background: item.color, width: `${Math.max(item.value / Math.max(...pieData.map(d => d.value), 1) * 100, 2)}%` }} />
                  </div>
                </div>
              </div>
            ))}
            {pieData.length === 0 && <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 24 }}>Нет данных</div>}
          </div>
        </div>
      </div>

      <div className="card mt-4">
        <div className="card-header">🏆 Топ учеников</div>
        <div style={{ padding: '0 20px 16px' }}>
          <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
            {['Неделя', 'Месяц', 'Всё время'].map(p => (
              <button key={p} onClick={() => setTopPeriod(p)}
                style={{
                  flex: 1, height: 40, borderRadius: 12, border: '2px solid #1B1B1B', cursor: 'pointer',
                  fontSize: 14, fontWeight: 600,
                  background: topPeriod === p ? '#111' : '#fff',
                  color: topPeriod === p ? '#fff' : 'var(--text)',
                  boxShadow: topPeriod === p ? 'none' : '0 2px 0 0 #1B1B1B',
                }}>
                {p}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
            <button onClick={() => setTopSubject(null)}
              style={{
                flexShrink: 0, height: 38, borderRadius: 19, border: '2px solid #1B1B1B', cursor: 'pointer',
                padding: '0 18px', fontSize: 13, fontWeight: 600,
                background: topSubject === null ? '#111' : '#fff',
                color: topSubject === null ? '#fff' : 'var(--text)',
                boxShadow: topSubject === null ? 'none' : '0 2px 0 0 #1B1B1B',
              }}>
              Все предметы
            </button>
            {topSubjects.map(s => (
              <button key={s.id} onClick={() => setTopSubject(s.id)}
                style={{
                  flexShrink: 0, height: 38, borderRadius: 19, border: '2px solid #1B1B1B', cursor: 'pointer',
                  padding: '0 18px', fontSize: 13, fontWeight: 600,
                  background: topSubject === s.id ? '#111' : '#fff',
                  color: topSubject === s.id ? '#fff' : 'var(--text)',
                  boxShadow: topSubject === s.id ? 'none' : '0 2px 0 0 #1B1B1B',
                }}>
                {s.icon} {s.name}
              </button>
            ))}
          </div>
        </div>
        {data.top_students && data.top_students.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Место</th>
                  <th>Ученик</th>
                  <th>Средний балл</th>
                  <th>Тестов</th>
                </tr>
              </thead>
              <tbody>
                {data.top_students.map((s, i) => (
                  <tr key={s.id}>
                    <td>
                      <span style={{ fontSize: 20 }}>
                        {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i + 1}`}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600 }}>{s.full_name || s.username}</td>
                    <td>
                      <span className={`badge badge-${s.avg_score >= 70 ? 'easy' : s.avg_score >= 40 ? 'medium' : 'hard'}`}>
                        {s.avg_score}%
                      </span>
                    </td>
                    <td>{s.test_count}</td>
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

      {/* Session detail modal */}
      {detailSubject && (
        <div className="modal-overlay" onClick={() => setDetailSubject(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 600 }}>
            <div className="modal-header">
              <h3>📋 {detailSubject} — результаты</h3>
              <button className="btn btn-sm" onClick={() => setDetailSubject(null)}><X size={16} /></button>
            </div>
            <div className="modal-body" style={{ maxHeight: 400, overflowY: 'auto' }}>
              {sessionsLoading ? (
                <div className="text-center"><div className="spinner"></div></div>
              ) : sessions.length === 0 ? (
                <p style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 24 }}>Нет результатов</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {sessions.map(s => (
                    <div key={s.id} style={{
                      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
                      borderRadius: 10, border: '1px solid var(--border)', cursor: 'pointer',
                    }}
                      onClick={() => { navigate(`/teacher/tests/${s.id}`); setDetailSubject(null) }}>
                      <div style={{
                        width: 42, height: 42, borderRadius: 10,
                        background: s.score_percent >= 70 ? '#D1FAE5' : s.score_percent >= 40 ? '#FEF3C7' : '#FEE2E2',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontWeight: 700, fontSize: 16, flexShrink: 0,
                        color: s.score_percent >= 70 ? '#059669' : s.score_percent >= 40 ? '#D97706' : '#DC2626',
                      }}>
                        {s.score_percent}%
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: 14 }}>{s.student_name || s.student_username}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                          {s.correct_answers}/{s.total_questions} · {s.completed_at ? new Date(s.completed_at).toLocaleDateString('ru-RU') : ''}
                        </div>
                      </div>
                      <ExternalLink size={16} strokeWidth={1.5} style={{ color: 'var(--text-secondary)', flexShrink: 0 }} />
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
