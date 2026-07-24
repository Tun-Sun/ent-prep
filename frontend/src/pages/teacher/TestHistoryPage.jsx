import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { testsAPI, subjectsAPI, groupsAPI } from '../../api'
import { Search, X, Filter, CalendarDays, BookOpen } from 'lucide-react'

export default function TestHistoryPage() {
  const [sessions, setSessions] = useState([])
  const [subjects, setSubjects] = useState([])
  const [groups, setGroups] = useState([])
  const [filterSubject, setFilterSubject] = useState('')
  const [filterGroupId, setFilterGroupId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [studentSearch, setStudentSearch] = useState('')
  const [selectedStudent, setSelectedStudent] = useState(null)
  const [studentResults, setStudentResults] = useState([])
  const [showDropdown, setShowDropdown] = useState(false)
  const [loading, setLoading] = useState(true)
  const [urlStudentFilter, setUrlStudentFilter] = useState(() => new URLSearchParams(window.location.search).get('student'))

  const selectedGroup = groups.find(g => g.id === Number(filterGroupId))

  useEffect(() => {
    subjectsAPI.list().then(res => setSubjects(Array.isArray(res.data) ? res.data : []))
    groupsAPI.list().then(res => setGroups(Array.isArray(res.data) ? res.data : []))
  }, [])

  useEffect(() => {
    setLoading(true)
    const params = {}
    if (filterSubject) params.subject = filterSubject
    if (selectedStudent) {
      params.student = selectedStudent.id
    } else if (urlStudentFilter) {
      params.student = urlStudentFilter
    }
    testsAPI.teacherHistory(params)
      .then(res => setSessions(Array.isArray(res.data) ? res.data : []))
      .finally(() => setLoading(false))
  }, [filterSubject, selectedStudent, urlStudentFilter])

  useEffect(() => {
    if (!studentSearch || studentSearch.length < 2) { setStudentResults([]); return }
    const timer = setTimeout(() => {
      groupsAPI.searchStudents(studentSearch, filterGroupId).then(res => {
        setStudentResults(Array.isArray(res.data) ? res.data : [])
      }).catch(() => {})
    }, 300)
    return () => clearTimeout(timer)
  }, [studentSearch, filterGroupId])

  const filtered = useMemo(() => {
    let result = sessions
    if (filterGroupId && selectedGroup) {
      result = result.filter(s => s.student_groups?.includes(selectedGroup.name))
    }
    if (dateFrom) {
      result = result.filter(s => {
        const d = s.completed_at || s.started_at
        return d && d.slice(0, 10) >= dateFrom
      })
    }
    if (dateTo) {
      result = result.filter(s => {
        const d = s.completed_at || s.started_at
        return d && d.slice(0, 10) <= dateTo
      })
    }
    if (studentSearch.trim() && !selectedStudent) {
      const q = studentSearch.trim().toLowerCase()
      result = result.filter(s =>
        (s.student_name || '').toLowerCase().includes(q) ||
        (s.student_username || '').toLowerCase().includes(q)
      )
    }
    return result
  }, [sessions, filterGroupId, dateFrom, dateTo, studentSearch, selectedStudent])

  const getScoreClass = (pct) => pct >= 70 ? '#16a34a' : pct >= 40 ? '#d97706' : '#dc2626'

  const filterActive = filterSubject || filterGroupId || dateFrom || dateTo || selectedStudent || studentSearch
  const clearFilters = () => {
    setFilterSubject(''); setFilterGroupId(''); setDateFrom(''); setDateTo('')
    setSelectedStudent(null); setStudentSearch(''); setShowDropdown(false); setUrlStudentFilter('')
  }

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 20 }}>
        <h1 className="page-title">Тесты учеников</h1>
        <p className="page-subtitle">Все завершённые тестовые сессии</p>
      </div>

      <div className="card" style={{ marginBottom: 20, padding: 20 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <CalendarDays size={12} strokeWidth={1.5} style={{ display: 'inline', marginRight: 4, verticalAlign: -1 }} />
              С
            </label>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff' }} />
          </div>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>По</label>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff' }} />
          </div>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <BookOpen size={12} strokeWidth={1.5} style={{ display: 'inline', marginRight: 4, verticalAlign: -1 }} />
              Предмет
            </label>
            <select value={filterSubject} onChange={e => setFilterSubject(e.target.value)}
              style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff', cursor: 'pointer', maxWidth: 160 }}>
              <option value="">Все предметы</option>
              {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <Filter size={12} strokeWidth={1.5} style={{ display: 'inline', marginRight: 4, verticalAlign: -1 }} />
              Группа
            </label>
            <select value={filterGroupId} onChange={e => setFilterGroupId(e.target.value)}
              style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff', cursor: 'pointer', maxWidth: 160 }}>
              <option value="">Все группы</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          <div style={{ position: 'relative', minWidth: 180 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <Search size={12} strokeWidth={1.5} style={{ display: 'inline', marginRight: 4, verticalAlign: -1 }} />
              Ученик
            </label>
            <div style={{ position: 'relative' }}>
              <input type="text" placeholder="Поиск..." value={studentSearch}
                onChange={e => { setStudentSearch(e.target.value); setShowDropdown(true); setSelectedStudent(null) }}
                onFocus={() => setShowDropdown(true)}
                onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
                style={{
                  width: '100%', height: 38, borderRadius: 10, border: '1px solid var(--border)',
                  padding: '0 12px', paddingRight: 30, fontSize: 13, background: '#fff',
                }} />
              {selectedStudent ? (
                <X size={14} style={{ position: 'absolute', right: 10, top: 12, cursor: 'pointer', color: 'var(--text-secondary)' }}
                  onClick={() => { setSelectedStudent(null); setStudentSearch('') }} />
              ) : (
                <Search size={14} style={{ position: 'absolute', right: 10, top: 12, color: 'var(--text-secondary)' }} />
              )}
            </div>
            {showDropdown && studentSearch.length >= 2 && studentResults.length > 0 && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100,
                background: '#fff', border: '1px solid var(--border)', borderRadius: 12,
                marginTop: 4, maxHeight: 200, overflowY: 'auto',
                boxShadow: 'var(--shadow-lg)',
              }}>
                {studentResults.map(st => (
                  <div key={st.id}
                    style={{ padding: '10px 14px', cursor: 'pointer', borderBottom: '1px solid #f0f0f0', fontSize: 14 }}
                    onMouseDown={() => { setSelectedStudent(st); setStudentSearch(st.full_name || st.username); setShowDropdown(false) }}>
                    {st.full_name || st.username} <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>@{st.username}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          {filterActive && (
            <button onClick={clearFilters}
              style={{
                height: 38, borderRadius: 10, border: '1px solid var(--border)',
                background: '#fff', padding: '0 14px', cursor: 'pointer',
                fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6,
              }}>
              <X size={14} /> Сбросить
            </button>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>
          Всего результатов: {filtered.length}
        </div>
        {loading ? (
          <div className="text-center py-4"><div className="spinner"></div></div>
        ) : filtered.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 32 }}>
            {sessions.length === 0 ? 'Тесты не найдены' : 'Нет результатов по выбранным фильтрам'}
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  <th style={{ textAlign: 'left', padding: '12px 16px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Дата сдачи</th>
                  <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Группа</th>
                  <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Ученик</th>
                  <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Предмет</th>
                  <th style={{ textAlign: 'center', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Вопросов</th>
                  <th style={{ textAlign: 'center', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Правильных</th>
                  <th style={{ textAlign: 'center', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Результат</th>
                  <th style={{ textAlign: 'center', padding: '12px 16px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s, i) => (
                  <tr key={s.id} style={{ borderBottom: '1px solid var(--border)', background: i % 2 === 0 ? '#fff' : 'rgba(0,0,0,0.02)' }}>
                    <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontSize: 13, whiteSpace: 'nowrap' }}>
                      {s.completed_at ? new Date(s.completed_at).toLocaleDateString() : (s.started_at ? new Date(s.started_at).toLocaleDateString() : '—')}
                    </td>
                    <td style={{ padding: '12px 8px', fontSize: 13 }}>
                      {s.student_groups?.length > 0 ? s.student_groups.join(', ') : '—'}
                    </td>
                    <td style={{ padding: '12px 8px', fontWeight: 600, fontSize: 14 }}>
                      {s.student_name || s.student_username}
                    </td>
                    <td style={{ padding: '12px 8px', fontSize: 13 }}>
                      {s.subject_icon} {s.subject_name}
                    </td>
                    <td style={{ textAlign: 'center', padding: '12px 8px', fontSize: 14 }}>{s.total_questions}</td>
                    <td style={{ textAlign: 'center', padding: '12px 8px', fontSize: 14 }}>{s.correct_answers}</td>
                    <td style={{ textAlign: 'center', padding: '12px 8px' }}>
                      <span style={{
                        padding: '3px 10px', borderRadius: 100, fontSize: 13, fontWeight: 700,
                        background: s.score_percent >= 70 ? 'rgba(16,185,129,0.1)' : s.score_percent >= 40 ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)',
                        color: s.score_percent >= 70 ? '#065F46' : s.score_percent >= 40 ? '#92400E' : '#991B1B',
                      }}>
                        {s.score_percent}%
                      </span>
                    </td>
                    <td style={{ textAlign: 'center', padding: '12px 16px' }}>
                      <Link to={`/teacher/tests/${s.id}`}
                        style={{
                          padding: '6px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600,
                          border: '1px solid var(--border)', textDecoration: 'none',
                          color: 'var(--text)', display: 'inline-block',
                        }}>
                        Подробнее
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
