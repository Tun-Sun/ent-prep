import { useState, useEffect } from 'react'
import { dashboardAPI, groupsAPI, subjectsAPI } from '../../api'
import { X, Users, Plus, Check, BookOpen, Search, Filter } from 'lucide-react'

export default function StudentsPage() {
  const [students, setStudents] = useState([])
  const [groups, setGroups] = useState([])
  const [allSubjects, setAllSubjects] = useState([])
  const [loading, setLoading] = useState(true)

  // Filters
  const [filterGroupId, setFilterGroupId] = useState('')
  const [filterSubjectId, setFilterSubjectId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  // UI state
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('avg_score')
  const [assignStudent, setAssignStudent] = useState(null)
  const [selectedGroup, setSelectedGroup] = useState('')
  const [subjectsStudent, setSubjectsStudent] = useState(null)
  const [selectedSubjects, setSelectedSubjects] = useState([])

  const loadData = () => {
    setLoading(true)
    const params = {}
    if (filterGroupId) params.group_id = filterGroupId
    if (filterSubjectId) params.subject_id = filterSubjectId
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    Promise.all([
      dashboardAPI.teacherStudents(params),
      groupsAPI.list(),
      subjectsAPI.list(),
    ])
      .then(([res1, res2, res3]) => {
        setStudents(res1.data)
        setGroups(res2.data)
        setAllSubjects(res3.data)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadData() }, [filterGroupId, filterSubjectId, dateFrom, dateTo])

  const handleAssign = async () => {
    if (!assignStudent || !selectedGroup) return
    try {
      await groupsAPI.addStudents(selectedGroup, [assignStudent])
      setAssignStudent(null); setSelectedGroup(''); loadData()
    } catch { alert('Ошибка добавления') }
  }

  const handleRemoveFromGroup = async (studentId, groupId) => {
    try {
      await groupsAPI.removeStudent(groupId, studentId)
      loadData()
    } catch { alert('Ошибка удаления') }
  }

  const openSubjects = (student) => {
    setSelectedSubjects(student.profile_subjects || [])
    setSubjectsStudent(student)
  }

  const toggleSubject = (id) => {
    setSelectedSubjects(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const saveSubjects = async () => {
    if (!subjectsStudent) return
    try {
      await groupsAPI.updateStudentSubjects(subjectsStudent.id, selectedSubjects)
      setSubjectsStudent(null)
      loadData()
    } catch { alert('Ошибка сохранения') }
  }

  const clearFilters = () => {
    setFilterGroupId(''); setFilterSubjectId(''); setDateFrom(''); setDateTo('')
  }

  const modalOverlay = { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }
  const modalContent = { background: '#F4EEDC', border: '2px solid #1B1B1B', borderRadius: 26, padding: 28, width: '100%', maxWidth: 400, boxShadow: '6px 6px 0 0 rgba(0,0,0,0.1)' }

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>

  const filtered = students
    .filter(s =>
      (s.full_name || s.username).toLowerCase().includes(search.toLowerCase()) ||
      (s.school || '').toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      if (sortBy === 'avg_score') return (b.avg_score || 0) - (a.avg_score || 0)
      if (sortBy === 'total_tests') return (b.total_tests || 0) - (a.total_tests || 0)
      return (a.full_name || a.username).localeCompare(b.full_name || b.username)
    })

  const hasFilters = filterGroupId || filterSubjectId || dateFrom || dateTo

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Ученики</h1>
        <p className="page-subtitle">Все ученики, их группы и прогресс по предметам</p>
      </div>

      {/* Filters */}
      <div className="card" style={{ padding: '16px 20px', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Группа</div>
            <select className="form-select" style={{ height: 38, fontSize: 13, minWidth: 150 }}
              value={filterGroupId} onChange={e => setFilterGroupId(e.target.value)}>
              <option value="">Все группы</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Предмет</div>
            <select className="form-select" style={{ height: 38, fontSize: 13, minWidth: 150 }}
              value={filterSubjectId} onChange={e => setFilterSubjectId(e.target.value)}>
              <option value="">Все предметы</option>
              {allSubjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>От</div>
            <input type="date" className="form-input" style={{ height: 38, fontSize: 13 }}
              value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>До</div>
            <input type="date" className="form-input" style={{ height: 38, fontSize: 13 }}
              value={dateTo} onChange={e => setDateTo(e.target.value)} />
          </div>
          {hasFilters && (
            <button className="btn btn-outline" style={{ height: 38, fontSize: 13, padding: '0 14px' }}
              onClick={clearFilters}>
              <X size={14} style={{ marginRight: 4 }} /> Сбросить
            </button>
          )}
        </div>
      </div>

      <div className="card">
        <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
          <input
            className="form-input"
            style={{ maxWidth: 300 }}
            placeholder="Поиск по имени или школе..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <select
            className="form-select"
            style={{ maxWidth: 200 }}
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
          >
            <option value="avg_score">По среднему баллу</option>
            <option value="total_tests">По кол-ву тестов</option>
            <option value="name">По имени</option>
          </select>
        </div>

        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Ученик</th>
                <th>Школа</th>
                <th>Группы</th>
                <th>Предметы</th>
                <th>Тестов</th>
                <th>Средний балл</th>
                <th>Прогресс по предметам</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(s => (
                <tr key={s.id}>
                  <td style={{ fontWeight: 600 }}>{s.full_name || s.username}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{s.school || '—'}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
                      {(s.groups || []).map(g => (
                        <span key={g.id} style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          padding: '2px 8px', borderRadius: 6, fontSize: 12,
                          background: '#EEF2FF', color: '#4338CA', fontWeight: 500,
                        }}>
                          <Users size={11} />
                          {g.name}
                          <X size={11} style={{ cursor: 'pointer', opacity: 0.6 }} onClick={() => handleRemoveFromGroup(s.id, g.id)} />
                        </span>
                      ))}
                      <button style={{
                        width: 22, height: 22, borderRadius: 6, border: '1px dashed var(--text-secondary)',
                        background: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center',
                        justifyContent: 'center', opacity: 0.6,
                      }} onClick={() => setAssignStudent(s.id)} title="Добавить в группу">
                        <Plus size={12} />
                      </button>
                    </div>
                  </td>
                  <td>
                    <button className="btn btn-outline" style={{ fontSize: 12, padding: '4px 10px' }}
                      onClick={() => openSubjects(s)}>
                      <BookOpen size={12} style={{ marginRight: 4 }} />
                      {(s.profile_subjects?.length || 0)} шт
                    </button>
                  </td>
                  <td>{s.total_tests}</td>
                  <td>
                    <span className={`badge badge-${s.avg_score >= 70 ? 'easy' : s.avg_score >= 40 ? 'medium' : 'hard'}`}>
                      {s.avg_score}%
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {Object.entries(s.subject_progress || {}).map(([name, score]) => (
                        <span key={name} style={{
                          padding: '4px 10px',
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 600,
                          background: score >= 70 ? '#D1FAE5' : score >= 40 ? '#FEF3C7' : '#FEE2E2',
                          color: score >= 70 ? '#065F46' : score >= 40 ? '#92400E' : '#991B1B',
                        }}>
                          {name}: {score}%
                        </span>
                      ))}
                    </div>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <a href={`/teacher/tests?student=${s.id}`} style={{ fontSize: 13, color: 'var(--primary)', fontWeight: 600 }}>Результаты</a>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={8} style={{ textAlign: 'center', padding: 32, color: 'var(--text-secondary)' }}>
                  Ученики не найдены
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Assign to group modal */}
      {assignStudent && (
        <div style={modalOverlay} onClick={() => setAssignStudent(null)}>
          <div style={modalContent} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div style={{ fontSize: 18, fontWeight: 700 }}>Добавить в группу</div>
              <X size={20} style={{ cursor: 'pointer' }} onClick={() => setAssignStudent(null)} />
            </div>
            <select value={selectedGroup} onChange={e => setSelectedGroup(e.target.value)}
              style={{ width: '100%', height: 44, borderRadius: 14, border: '2px solid #1B1B1B', padding: '0 14px', fontSize: 15, background: '#fff', marginBottom: 14 }}>
              <option value="">Выберите группу</option>
              {groups.filter(g => !students.find(s => s.id === assignStudent)?.groups?.find(gg => gg.id === g.id)).map(g => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
            <button className="btn btn-primary" style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
              onClick={handleAssign} disabled={!selectedGroup}>
              <Check size={16} /> Добавить
            </button>
          </div>
        </div>
      )}

      {/* Subjects modal */}
      {subjectsStudent && (
        <div style={modalOverlay} onClick={() => setSubjectsStudent(null)}>
          <div style={{ ...modalContent, maxWidth: 480 }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div style={{ fontSize: 18, fontWeight: 700 }}>
                Предметы: {subjectsStudent.full_name || subjectsStudent.username}
              </div>
              <X size={20} style={{ cursor: 'pointer' }} onClick={() => setSubjectsStudent(null)} />
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 14 }}>
              Обязательные предметы всегда включены. Выберите профильные.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 300, overflowY: 'auto', marginBottom: 16 }}>
              {allSubjects.map(s => {
                const isMandatory = s.subject_type === 'mandatory'
                const isSelected = selectedSubjects.includes(s.id)
                return (
                  <label key={s.id} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
                    borderRadius: 10, cursor: 'pointer',
                    border: isSelected ? '2px solid var(--primary)' : '1px solid var(--border)',
                    background: isSelected ? '#eef2ff' : '#fafafa',
                    opacity: isMandatory ? 0.7 : 1,
                  }}>
                    <input type="checkbox" checked={isSelected || isMandatory}
                      disabled={isMandatory}
                      onChange={() => toggleSubject(s.id)}
                      style={{ width: 18, height: 18, cursor: isMandatory ? 'not-allowed' : 'pointer' }} />
                    <span style={{ fontSize: 18 }}>{s.icon}</span>
                    <span style={{ fontWeight: 500, fontSize: 14, flex: 1 }}>{s.name}</span>
                    {isMandatory && <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>обязательный</span>}
                  </label>
                )
              })}
            </div>
            <button className="btn btn-primary" style={{ width: '100%' }} onClick={saveSubjects}>
              Сохранить
            </button>
          </div>
        </div>
      )}
    </div>
  )
}