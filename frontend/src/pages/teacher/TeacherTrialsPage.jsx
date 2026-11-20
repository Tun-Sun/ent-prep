import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { testsAPI, groupsAPI, subjectsAPI } from '../../api'
import { ClipboardList, CheckCircle2, XCircle, Clock, KeyRound, CalendarDays, Users } from 'lucide-react'

const fmt = (value) => value
  ? new Date(value).toLocaleString('ru-RU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
  : '—'

export default function TeacherTrialsPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('stats')
  const [groups, setGroups] = useState([])
  const [trials, setTrials] = useState([])
  const [groupId, setGroupId] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([groupsAPI.list(), subjectsAPI.trials()])
      .then(([g, t]) => {
        const list = Array.isArray(g.data) ? g.data : []
        const variants = Array.isArray(t.data) ? t.data : []
        setGroups(list)
        setTrials(variants)
        setGroupId(prev => prev || String(list[0]?.id || ''))
        setSubjectId(prev => prev || String(variants[0]?.id || ''))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const loadStats = () => {
    if (!groupId || !subjectId) { setStats(null); return }
    setLoading(true)
    setError('')
    testsAPI.trialAccessStats({ group_id: groupId, subject_id: subjectId })
      .then(res => setStats(res.data))
      .catch(err => setError(err.response?.data?.error || 'Не удалось загрузить статистику'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadStats() }, [groupId, subjectId])

  const setAccess = async (row, open) => {
    setBusyId(row.student_id)
    setError('')
    try {
      if (open) {
        await testsAPI.grantTrialAccess({
          student_id: row.student_id, subject_id: Number(subjectId),
          note: 'Открыто тренером после дедлайна',
        })
      } else {
        await testsAPI.revokeTrialAccess(row.student_id, Number(subjectId))
      }
      await loadStats()
    } catch (err) {
      setError(err.response?.data?.error || 'Не удалось изменить доступ')
    } finally {
      setBusyId(null)
    }
  }

  if (loading && !stats) return <div className="text-center mt-8"><div className="spinner"></div></div>

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Пробные тесты</h1>
          <p className="page-subtitle">Сроки, доступ и сдача пробных вариантов</p>
        </div>
        <button className="btn btn-outline" onClick={() => navigate(-1)}>Назад</button>
      </div>

      <div className="tabs" style={{ marginBottom: 20 }}>
        <button className={`tab ${tab === 'stats' ? 'active' : ''}`} onClick={() => setTab('stats')}>
          <Users size={18} strokeWidth={1.5} /> Доступ и статистика
        </button>
        <button className={`tab ${tab === 'schedule' ? 'active' : ''}`} onClick={() => setTab('schedule')}>
          <CalendarDays size={18} strokeWidth={1.5} /> Расписание
        </button>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}

      {tab === 'stats' && (
        <>
          <div className="card" style={{ padding: 16, marginBottom: 20 }}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: 4 }}>Группа</label>
                <select className="form-select" value={groupId} onChange={e => setGroupId(e.target.value)}
                  style={{ minWidth: 200 }}>
                  <option value="">Выберите группу</option>
                  {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: 4 }}>Пробный вариант</label>
                <select className="form-select" value={subjectId} onChange={e => setSubjectId(e.target.value)}
                  style={{ minWidth: 240 }}>
                  <option value="">Выберите вариант</option>
                  {trials.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              <button className="btn btn-outline" onClick={loadStats}>Обновить</button>
            </div>
          </div>

          {stats && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 20 }}>
                {[
                  { label: 'В группе', value: stats.summary.total, color: 'var(--text)' },
                  { label: 'Сдали', value: stats.summary.submitted, color: '#059669' },
                  { label: 'Не сдали', value: stats.summary.not_submitted, color: '#DC2626' },
                  { label: 'Доступ открыт вручную', value: stats.summary.manual_access, color: '#4F46E5' },
                ].map(card => (
                  <div key={card.label} className="d-card" style={{ padding: '16px 20px', textAlign: 'center' }}>
                    <div style={{ fontSize: 28, fontWeight: 800, color: card.color }}>{card.value}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600 }}>{card.label}</div>
                  </div>
                ))}
              </div>

              <div style={{
                padding: '10px 16px', borderRadius: 'var(--radius)', marginBottom: 16,
                background: stats.subject.is_open_now ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
                display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, flexWrap: 'wrap',
              }}>
                <Clock size={15} strokeWidth={1.5} />
                <strong>{stats.subject.name}</strong>
                <span style={{ color: 'var(--text-secondary)' }}>
                  {stats.subject.is_open_now ? 'Вариант открыт' : 'Вариант закрыт по расписанию'}
                </span>
                <span style={{ color: 'var(--text-secondary)' }}>
                  с {fmt(stats.subject.available_from)} · до {fmt(stats.subject.available_until)}
                </span>
              </div>

              <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <div className="table-container">
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border)' }}>
                        {['Ученик', 'Статус', 'Дата сдачи', 'Балл', 'Доступ', ''].map(h => (
                          <th key={h} style={{ textAlign: 'left', padding: '12px 16px', fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {stats.results.map(row => (
                        <tr key={row.student_id} style={{ borderBottom: '1px solid var(--border)' }}>
                          <td style={{ padding: '12px 16px', fontWeight: 600, fontSize: 14 }}>
                            {row.student_name}
                            {!row.is_active && <span className="badge badge-hard" style={{ marginLeft: 8, fontSize: 9 }}>деактивирован</span>}
                          </td>
                          <td style={{ padding: '12px 16px' }}>
                            <span className={`badge ${row.submitted ? 'badge-easy' : 'badge-hard'}`}
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                              {row.submitted ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                              {row.submitted ? 'Сдал' : 'Не сдал'}
                            </span>
                          </td>
                          <td style={{ padding: '12px 16px', fontSize: 13, color: 'var(--text-secondary)' }}>
                            {fmt(row.completed_at)}
                          </td>
                          <td style={{ padding: '12px 16px', fontSize: 13, fontWeight: 600 }}>
                            {row.score_percent == null ? '—' : `${row.score_percent}%`}
                          </td>
                          <td style={{ padding: '12px 16px' }}>
                            <span className={`badge ${row.manual_access ? 'badge-medium' : ''}`} style={{ fontSize: 9 }}>
                              {row.manual_access ? 'Открыт вручную' : 'По расписанию'}
                            </span>
                          </td>
                          <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                            <button className={row.manual_access ? 'btn btn-outline btn-sm' : 'btn btn-primary btn-sm'}
                              disabled={busyId === row.student_id}
                              onClick={() => setAccess(row, !row.manual_access)}>
                              <KeyRound size={13} style={{ marginRight: 5 }} />
                              {busyId === row.student_id ? '…' : row.manual_access ? 'Закрыть доступ' : 'Открыть доступ'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </>
      )}

      {tab === 'schedule' && (
        <div className="card">
          <div style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 18, fontWeight: 800, marginBottom: 6 }}>Расписание пробных вариантов</h3>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>
              Даты открытия и закрытия выставляет администратор в разделе «Админ-панель → Пробные».
              Здесь расписание показано для справки.
            </p>
          </div>
          <div className="table-container">
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Вариант', 'Открыт с', 'Закрыт до', 'Статус'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '12px 16px', fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trials.map(s => (
                  <tr key={s.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 600, fontSize: 14 }}>{s.name}</td>
                    <td style={{ padding: '12px 16px', fontSize: 13 }}>{fmt(s.available_from)}</td>
                    <td style={{ padding: '12px 16px', fontSize: 13 }}>{fmt(s.available_until)}</td>
                    <td style={{ padding: '12px 16px' }}>
                      <span className={`badge ${s.status === 'open' ? 'badge-easy' : s.status === 'upcoming' ? 'badge-medium' : 'badge-hard'}`}>
                        {s.status === 'open' ? 'Открыт' : s.status === 'upcoming' ? 'Скоро' : s.status === 'empty' ? 'Готовится' : 'Закрыт'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
