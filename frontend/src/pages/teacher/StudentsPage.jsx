import { useState, useEffect } from 'react'
import { dashboardAPI, groupsAPI, subjectsAPI, authAPI } from '../../api'
import { X, Users, Plus, Check, BookOpen, Search, Filter, GraduationCap, School, BarChart3, Trophy, FileDown, KeyRound } from 'lucide-react'

export default function StudentsPage() {
  const [students, setStudents] = useState([])
  const [groups, setGroups] = useState([])
  const [allSubjects, setAllSubjects] = useState([])
  const [loading, setLoading] = useState(true)

  const [filterGroupId, setFilterGroupId] = useState('')
  const [filterSubjectId, setFilterSubjectId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('avg_score')
  const [assignStudent, setAssignStudent] = useState(null)
  const [selectedGroup, setSelectedGroup] = useState('')
  const [subjectsStudent, setSubjectsStudent] = useState(null)
  const [selectedSubjects, setSelectedSubjects] = useState([])
  const [resetStudent, setResetStudent] = useState(null)
  const [resetResult, setResetResult] = useState(null)
  const [resetting, setResetting] = useState(false)

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

  const downloadReport = async (student) => {
    try {
      const res = await dashboardAPI.studentReportPdf(student.id)
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `report_${student.username || student.id}.pdf`
      a.click()
      window.URL.revokeObjectURL(url)
    } catch {
      alert('Не удалось сформировать PDF-отчёт')
    }
  }

  const doResetPassword = async () => {
    if (!resetStudent || resetting) return
    setResetting(true)
    try {
      const res = await authAPI.resetStudentPassword(resetStudent.id)
      setResetResult(res.data)
    } catch (err) {
      alert(err.response?.data?.error || 'Ошибка сброса пароля')
      setResetStudent(null)
    } finally {
      setResetting(false)
    }
  }

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

      <div className="card" style={{ padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <Filter size={12} strokeWidth={1.5} style={{ display: 'inline', marginRight: 4, verticalAlign: -1 }} />
              Группа
            </div>
            <select value={filterGroupId} onChange={e => setFilterGroupId(e.target.value)}
              style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff', cursor: 'pointer', minWidth: 150 }}>
              <option value="">Все группы</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <BookOpen size={12} strokeWidth={1.5} style={{ display: 'inline', marginRight: 4, verticalAlign: -1 }} />
              Предмет
            </div>
            <select value={filterSubjectId} onChange={e => setFilterSubjectId(e.target.value)}
              style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff', cursor: 'pointer', minWidth: 150 }}>
              <option value="">Все предметы</option>
              {allSubjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>От</div>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff' }} />
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>До</div>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff' }} />
          </div>
          {hasFilters && (
            <button onClick={clearFilters}
              style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', background: '#fff', padding: '0 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              <X size={14} /> Сбросить
            </button>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 12 }}>
          <div style={{ position: 'relative', flex: 1, maxWidth: 280 }}>
            <Search size={14} style={{ position: 'absolute', left: 12, top: 12, color: 'var(--text-secondary)' }} />
            <input type="text" placeholder="Поиск по имени или школе..." value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ width: '100%', height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px 0 34px', fontSize: 13, background: '#fff' }} />
          </div>
          <select value={sortBy} onChange={e => setSortBy(e.target.value)}
            style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff', cursor: 'pointer', maxWidth: 200 }}>
            <option value="avg_score">По среднему баллу</option>
            <option value="total_tests">По кол-ву тестов</option>
            <option value="name">По имени</option>
          </select>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th style={{ textAlign: 'left', padding: '12px 16px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Ученик</th>
                <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Школа</th>
                <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Группы</th>
                <th style={{ textAlign: 'center', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Предметы</th>
                <th style={{ textAlign: 'center', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Тестов</th>
                <th style={{ textAlign: 'center', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Средний балл</th>
                <th style={{ textAlign: 'left', padding: '12px 8px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Прогресс</th>
                <th style={{ textAlign: 'right', padding: '12px 16px', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s, i) => (
                <tr key={s.id} style={{ borderBottom: '1px solid var(--border)', background: i % 2 === 0 ? '#fff' : 'rgba(0,0,0,0.02)' }}>
                  <td style={{ padding: '14px 16px', fontWeight: 600, fontSize: 14 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <GraduationCap size={16} strokeWidth={1.5} style={{ color: 'var(--text-secondary)', flexShrink: 0 }} />
                      {s.full_name || s.username}
                    </div>
                  </td>
                  <td style={{ padding: '14px 8px', color: 'var(--text-secondary)', fontSize: 13 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <School size={14} strokeWidth={1.5} style={{ flexShrink: 0 }} />
                      {s.school || '—'}
                    </div>
                  </td>
                  <td style={{ padding: '14px 8px' }}>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
                      {(s.groups || []).map(g => (
                        <span key={g.id} style={{
                          display: 'inline-flex', alignItems: 'center', gap: 3,
                          padding: '2px 8px', borderRadius: 6, fontSize: 12,
                          background: 'rgba(99,102,241,0.06)', color: 'var(--primary)', fontWeight: 500,
                        }}>
                          <Users size={11} />
                          {g.name}
                          <X size={11} style={{ cursor: 'pointer', opacity: 0.5 }}
                            onClick={() => handleRemoveFromGroup(s.id, g.id)} />
                        </span>
                      ))}
                      <button style={{
                        width: 22, height: 22, borderRadius: 6, border: '1px dashed var(--text-secondary)',
                        background: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center',
                        justifyContent: 'center', opacity: 0.5,
                      }} onClick={() => setAssignStudent(s.id)} title="Добавить в группу">
                        <Plus size={12} />
                      </button>
                    </div>
                  </td>
                  <td style={{ textAlign: 'center', padding: '14px 8px' }}>
                    <button onClick={() => openSubjects(s)}
                      style={{
                        padding: '4px 12px', borderRadius: 8, border: '1px solid var(--border)',
                        fontSize: 12, fontWeight: 600, cursor: 'pointer', background: '#fff', color: 'var(--text)',
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                      }}>
                      <BookOpen size={12} strokeWidth={1.5} />
                      {s.profile_subjects?.length || 0} шт
                    </button>
                  </td>
                  <td style={{ textAlign: 'center', padding: '14px 8px', fontSize: 14 }}>{s.total_tests}</td>
                  <td style={{ textAlign: 'center', padding: '14px 8px' }}>
                    <span style={{
                      padding: '3px 10px', borderRadius: 100, fontSize: 13, fontWeight: 700,
                      background: s.avg_score >= 70 ? 'rgba(16,185,129,0.1)' : s.avg_score >= 40 ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)',
                      color: s.avg_score >= 70 ? '#065F46' : s.avg_score >= 40 ? '#92400E' : '#991B1B',
                    }}>
                      {s.avg_score}%
                    </span>
                  </td>
                  <td style={{ padding: '14px 8px' }}>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {Object.entries(s.subject_progress || {}).map(([name, score]) => (
                        <span key={name} style={{
                          padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                          background: score >= 70 ? 'rgba(16,185,129,0.1)' : score >= 40 ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)',
                          color: score >= 70 ? '#065F46' : score >= 40 ? '#92400E' : '#991B1B',
                        }}>
                          {name}: {score}%
                        </span>
                      ))}
                    </div>
                  </td>
                  <td style={{ textAlign: 'right', padding: '14px 16px', whiteSpace: 'nowrap' }}>
                    <button onClick={() => downloadReport(s)} title="PDF-отчёт для родителей"
                      style={{
                        border: 'none', background: 'transparent', cursor: 'pointer',
                        color: 'var(--primary)', marginRight: 10, verticalAlign: 'middle',
                        display: 'inline-flex', alignItems: 'center',
                      }}>
                      <FileDown size={16} strokeWidth={1.8} />
                    </button>
                    <button onClick={() => { setResetStudent(s); setResetResult(null) }} title="Сбросить пароль"
                      style={{
                        border: 'none', background: 'transparent', cursor: 'pointer',
                        color: 'var(--text-secondary)', marginRight: 10, verticalAlign: 'middle',
                        display: 'inline-flex', alignItems: 'center',
                      }}>
                      <KeyRound size={16} strokeWidth={1.8} />
                    </button>
                    <a href={`/teacher/tests?student=${s.id}`}
                      style={{ fontSize: 13, color: 'var(--primary)', fontWeight: 600, textDecoration: 'none' }}>
                      Результаты
                    </a>
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

      {assignStudent && (
        <div className="modal-overlay" onClick={() => setAssignStudent(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}
            style={{ maxWidth: 400, borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: 18, fontWeight: 800 }}>Добавить в группу</h3>
              <button className="btn btn-sm" onClick={() => setAssignStudent(null)}
                style={{ borderRadius: 8, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X size={16} />
              </button>
            </div>
            <div style={{ padding: '12px 20px' }}>
              <select value={selectedGroup} onChange={e => setSelectedGroup(e.target.value)}
                style={{ width: '100%', height: 42, borderRadius: 10, border: '1px solid var(--border)', padding: '0 14px', fontSize: 14, background: '#fff', cursor: 'pointer', marginBottom: 14 }}>
                <option value="">Выберите группу</option>
                {groups.filter(g => !students.find(s => s.id === assignStudent)?.groups?.find(gg => gg.id === g.id)).map(g => (
                  <option key={g.id} value={g.id}>{g.name}</option>
                ))}
              </select>
              <button className="btn btn-primary" onClick={handleAssign} disabled={!selectedGroup}
                style={{ width: '100%', borderRadius: 12, padding: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, opacity: !selectedGroup ? 0.5 : 1 }}>
                <Check size={16} /> Добавить
              </button>
            </div>
          </div>
        </div>
      )}

      {subjectsStudent && (
        <div className="modal-overlay" onClick={() => setSubjectsStudent(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}
            style={{ maxWidth: 480, borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: 18, fontWeight: 800 }}>Предметы: {subjectsStudent.full_name || subjectsStudent.username}</h3>
              <button className="btn btn-sm" onClick={() => setSubjectsStudent(null)}
                style={{ borderRadius: 8, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X size={16} />
              </button>
            </div>
            <div style={{ padding: '12px 20px' }}>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 14 }}>
                Обязательные предметы всегда включены. Выберите профильные.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 300, overflowY: 'auto', marginBottom: 16 }}>
                {allSubjects.map(s => {
                  const isMandatory = s.subject_type === 'mandatory'
                  const isSelected = selectedSubjects.includes(s.id)
                  return (
                    <label key={s.id} style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
                      borderRadius: 10, cursor: 'pointer',
                      border: isSelected ? '1.5px solid var(--primary)' : '1px solid var(--border)',
                      background: isSelected ? 'rgba(36,59,130,0.04)' : '#fff',
                      opacity: isMandatory ? 0.7 : 1,
                    }}>
                      <input type="checkbox" checked={isSelected || isMandatory}
                        disabled={isMandatory}
                        onChange={() => toggleSubject(s.id)}
                        style={{ width: 18, height: 18, cursor: isMandatory ? 'not-allowed' : 'pointer', accentColor: 'var(--primary)' }} />
                      <span style={{ fontSize: 18 }}>{s.icon}</span>
                      <span style={{ fontWeight: 500, fontSize: 14, flex: 1 }}>{s.name}</span>
                      {isMandatory && <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>обязательный</span>}
                    </label>
                  )
                })}
              </div>
              <button className="btn btn-primary" onClick={saveSubjects}
                style={{ width: '100%', borderRadius: 12, padding: '10px' }}>
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
      {resetStudent && (
        <div className="modal-overlay" onClick={() => { setResetStudent(null); setResetResult(null) }}>
          <div className="modal" onClick={e => e.stopPropagation()}
            style={{ maxWidth: 420, borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: 18, fontWeight: 800 }}>Сброс пароля</h3>
              <button className="btn btn-sm" onClick={() => { setResetStudent(null); setResetResult(null) }}
                style={{ borderRadius: 8, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X size={16} />
              </button>
            </div>
            <div style={{ padding: '12px 20px' }}>
              {resetResult ? (
                <>
                  <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 12 }}>
                    Новый пароль для <b>{resetResult.full_name || resetResult.username}</b> (@{resetResult.username}):
                  </p>
                  <div style={{
                    background: 'rgba(36,59,130,0.06)', borderRadius: 12, padding: '14px 18px',
                    fontSize: 20, fontWeight: 800, fontFamily: 'monospace', textAlign: 'center',
                    letterSpacing: 2, marginBottom: 12, userSelect: 'all',
                  }}>
                    {resetResult.new_password}
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 14 }}>
                    Пароль показан только один раз — передайте его ученику и попросите сменить в настройках.
                  </p>
                  <button className="btn btn-primary"
                    onClick={() => { navigator.clipboard?.writeText(resetResult.new_password); }}
                    style={{ width: '100%', borderRadius: 12, padding: '10px', marginBottom: 8 }}>
                    Скопировать
                  </button>
                  <button className="btn btn-outline"
                    onClick={() => { setResetStudent(null); setResetResult(null) }}
                    style={{ width: '100%', borderRadius: 12, padding: '10px' }}>
                    Готово
                  </button>
                </>
              ) : (
                <>
                  <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 16 }}>
                    Сгенерировать новый пароль для <b>{resetStudent.full_name || resetStudent.username}</b>?
                    Текущий пароль перестанет работать.
                  </p>
                  <button className="btn btn-primary" onClick={doResetPassword} disabled={resetting}
                    style={{ width: '100%', borderRadius: 12, padding: '10px', opacity: resetting ? 0.6 : 1 }}>
                    {resetting ? 'Генерируем...' : 'Сгенерировать пароль'}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
