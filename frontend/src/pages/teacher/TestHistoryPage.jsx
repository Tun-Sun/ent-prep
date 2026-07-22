import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { testsAPI, subjectsAPI, groupsAPI } from '../../api'
import { Search, X } from 'lucide-react'

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

  const selectedGroup = groups.find(g => g.id === Number(filterGroupId))

  useEffect(() => {
    subjectsAPI.list().then(res => setSubjects(Array.isArray(res.data) ? res.data : []))
    groupsAPI.list().then(res => setGroups(Array.isArray(res.data) ? res.data : []))
  }, [])

  useEffect(() => {
    setLoading(true)
    const params = {}
    if (filterSubject) params.subject = filterSubject
    if (selectedStudent) params.student = selectedStudent.id
    testsAPI.teacherHistory(params)
      .then(res => setSessions(Array.isArray(res.data) ? res.data : []))
      .finally(() => setLoading(false))
  }, [filterSubject, selectedStudent])

  // Student search (filter by group if selected)
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

  const getScoreClass = (pct) => pct >= 70 ? 'success' : pct >= 40 ? 'warning' : 'danger'

  const filterActive = filterSubject || filterGroupId || dateFrom || dateTo || selectedStudent || studentSearch
  const clearFilters = () => {
    setFilterSubject(''); setFilterGroupId(''); setDateFrom(''); setDateTo('')
    setSelectedStudent(null); setStudentSearch(''); setShowDropdown(false)
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Тесты учеников</h1>
        <p className="page-subtitle">Все завершённые тестовые сессии</p>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>С</label>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              style={{ height: 40, borderRadius: 12, border: '1.5px solid var(--border)', padding: '0 12px', fontSize: 14, background: '#fff' }} />
          </div>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>По</label>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              style={{ height: 40, borderRadius: 12, border: '1.5px solid var(--border)', padding: '0 12px', fontSize: 14, background: '#fff' }} />
          </div>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Предмет</label>
            <select className="form-select" style={{ maxWidth: 180 }} value={filterSubject} onChange={e => setFilterSubject(e.target.value)}>
              <option value="">Все предметы</option>
              {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Группа</label>
            <select className="form-select" style={{ maxWidth: 180 }} value={filterGroupId} onChange={e => setFilterGroupId(e.target.value)}>
              <option value="">Все группы</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          <div style={{ position: 'relative', minWidth: 200 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Ученик</label>
            <div style={{ position: 'relative' }}>
              <input type="text" placeholder="Поиск ученика..." value={studentSearch}
                onChange={e => { setStudentSearch(e.target.value); setShowDropdown(true); setSelectedStudent(null) }}
                onFocus={() => setShowDropdown(true)}
                onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
                style={{ width: '100%', height: 40, borderRadius: 12, border: '1.5px solid var(--border)', padding: '0 12px', paddingRight: 30, fontSize: 14, background: '#fff' }} />
              {selectedStudent ? (
                <X size={16} style={{ position: 'absolute', right: 10, top: 12, cursor: 'pointer', color: 'var(--text-secondary)' }}
                  onClick={() => { setSelectedStudent(null); setStudentSearch('') }} />
              ) : (
                <Search size={16} style={{ position: 'absolute', right: 10, top: 12, color: 'var(--text-secondary)' }} />
              )}
            </div>
            {showDropdown && studentSearch.length >= 2 && studentResults.length > 0 && (
              <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100, background: '#fff', border: '2px solid #1B1B1B', borderRadius: 12, marginTop: 4, maxHeight: 200, overflowY: 'auto', boxShadow: '3px 3px 0 0 rgba(0,0,0,0.08)' }}>
                {studentResults.map(st => (
                  <div key={st.id} style={{ padding: '10px 14px', cursor: 'pointer', borderBottom: '1px solid #f0f0f0', fontSize: 14 }}
                    onMouseDown={() => { setSelectedStudent(st); setStudentSearch(st.full_name || st.username); setShowDropdown(false) }}>
                    {st.full_name || st.username} <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>@{st.username}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          {filterActive && (
            <button onClick={clearFilters} style={{ height: 40, borderRadius: 12, border: '1.5px solid var(--border)', background: '#fff', padding: '0 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              <X size={14} /> Сбросить
            </button>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">Всего результатов: {filtered.length}</div>
        {loading ? (
          <div className="text-center"><div className="spinner"></div></div>
        ) : filtered.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 32 }}>
            {sessions.length === 0 ? 'Тесты не найдены' : 'Нет результатов по выбранным фильтрам'}
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="table" style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--border)' }}>
                  <th style={{ textAlign: 'left', padding: '12px 8px' }}>Дата сдачи</th>
                  <th style={{ textAlign: 'left', padding: '12px 8px' }}>Группа</th>
                  <th style={{ textAlign: 'left', padding: '12px 8px' }}>Ученик</th>
                  <th style={{ textAlign: 'left', padding: '12px 8px' }}>Предмет</th>
                  <th style={{ textAlign: 'center', padding: '12px 8px' }}>Вопросов</th>
                  <th style={{ textAlign: 'center', padding: '12px 8px' }}>Правильных</th>
                  <th style={{ textAlign: 'center', padding: '12px 8px' }}>Результат</th>
                  <th style={{ textAlign: 'center', padding: '12px 8px' }}></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(s => (
                  <tr key={s.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '12px 8px', color: 'var(--text-secondary)', fontSize: 13, whiteSpace: 'nowrap' }}>
                      {s.completed_at ? new Date(s.completed_at).toLocaleDateString() : (s.started_at ? new Date(s.started_at).toLocaleDateString() : '—')}
                    </td>
                    <td style={{ padding: '12px 8px', fontSize: 13 }}>
                      {s.student_groups?.length > 0 ? s.student_groups.join(', ') : '—'}
                    </td>
                    <td style={{ padding: '12px 8px' }}>
                      <strong>{s.student_name || s.student_username}</strong>
                    </td>
                    <td style={{ padding: '12px 8px' }}>
                      {s.subject_icon} {s.subject_name}
                    </td>
                    <td style={{ textAlign: 'center', padding: '12px 8px' }}>{s.total_questions}</td>
                    <td style={{ textAlign: 'center', padding: '12px 8px' }}>{s.correct_answers}</td>
                    <td style={{ textAlign: 'center', padding: '12px 8px' }}>
                      <span className={`badge badge-${getScoreClass(s.score_percent)}`}>
                        {s.score_percent}%
                      </span>
                    </td>
                    <td style={{ textAlign: 'center', padding: '12px 8px' }}>
                      <Link
                        to={`/teacher/tests/${s.id}`}
                        className="btn btn-outline"
                        style={{ padding: '6px 12px', fontSize: 13 }}
                      >
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