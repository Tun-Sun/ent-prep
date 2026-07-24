import { useState, useEffect } from 'react'
import { groupsAPI } from '../../api'
import { Plus, X, Search, Users, Trash2, Layers, UserPlus, ArrowRight, BookOpen } from 'lucide-react'

export default function GroupsPage() {
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [manageGroup, setManageGroup] = useState(null)
  const [studentSearch, setStudentSearch] = useState('')
  const [studentResults, setStudentResults] = useState([])
  const [groupDetail, setGroupDetail] = useState(null)
  const [showCreateStudent, setShowCreateStudent] = useState(false)
  const [newStudent, setNewStudent] = useState({ username: '', password: '', full_name: '' })
  const [moveTarget, setMoveTarget] = useState(null)

  const loadGroups = () => {
    setLoading(true)
    groupsAPI.list()
      .then(res => setGroups(Array.isArray(res.data) ? res.data : []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadGroups() }, [])

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      await groupsAPI.create(newName.trim())
      setNewName(''); setShowCreate(false); loadGroups()
    } catch { alert('Ошибка создания') }
  }

  const handleDelete = async (id) => {
    if (!confirm('Удалить группу?')) return
    try {
      await groupsAPI.delete(id)
      if (manageGroup?.id === id) { setManageGroup(null); setGroupDetail(null) }
      loadGroups()
    } catch { alert('Ошибка удаления') }
  }

  const openManage = async (group) => {
    setManageGroup(group)
    try {
      const res = await groupsAPI.detail(group.id)
      setGroupDetail(res.data)
      setStudentSearch(''); setStudentResults([])
    } catch { alert('Ошибка загрузки') }
  }

  useEffect(() => {
    if (!studentSearch || studentSearch.length < 2) { setStudentResults([]); return }
    const timer = setTimeout(() => {
      groupsAPI.searchStudents(studentSearch).then(res => {
        setStudentResults(Array.isArray(res.data) ? res.data : [])
      }).catch(() => {})
    }, 300)
    return () => clearTimeout(timer)
  }, [studentSearch])

  const addStudent = async (student) => {
    if (!manageGroup) return
    try {
      await groupsAPI.addStudents(manageGroup.id, [student.id])
      openManage(manageGroup)
    } catch { alert('Ошибка добавления') }
  }

  const removeStudent = async (studentId) => {
    if (!manageGroup) return
    try {
      await groupsAPI.removeStudent(manageGroup.id, studentId)
      openManage(manageGroup)
    } catch { alert('Ошибка удаления') }
  }

  const moveStudent = async (studentId, fromGroupId, toGroupId) => {
    try {
      await groupsAPI.removeStudent(fromGroupId, studentId)
      await groupsAPI.addStudents(toGroupId, [studentId])
      openManage(manageGroup)
      setMoveTarget(null)
    } catch { alert('Ошибка перемещения') }
  }

  const handleCreateStudent = async () => {
    if (!newStudent.username || !newStudent.password) return
    try {
      await groupsAPI.createStudent({
        ...newStudent, group_id: manageGroup?.id,
      })
      setNewStudent({ username: '', password: '', full_name: '' })
      setShowCreateStudent(false)
      openManage(manageGroup)
    } catch (e) {
      alert(e.response?.data?.error || 'Ошибка создания')
    }
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Группы</h1>
          <p className="page-subtitle">Объединяйте учеников в группы</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}
          style={{ borderRadius: 12, padding: '10px 18px', display: 'flex', alignItems: 'center', gap: 6 }}>
          <Plus size={16} /> Создать группу
        </button>
      </div>

      {loading ? (
        <div className="text-center mt-8"><div className="spinner"></div></div>
      ) : groups.length === 0 ? (
        <div className="card" style={{ padding: 60, textAlign: 'center' }}>
          <Layers size={48} strokeWidth={1.5} style={{ color: 'var(--text-secondary)', marginBottom: 16, opacity: 0.3 }} />
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>Нет групп</div>
          <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 20 }}>Создайте первую группу, чтобы объединять учеников</div>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}
            style={{ borderRadius: 12, padding: '10px 20px', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Plus size={16} /> Создать группу
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
          {groups.map(g => (
            <div key={g.id} className="card" style={{ padding: 20, cursor: 'pointer' }}
              onClick={() => openManage(g)}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 12,
                  background: 'rgba(99,102,241,0.08)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Layers size={20} strokeWidth={1.5} style={{ color: 'var(--primary)' }} />
                </div>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>{g.name}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, color: 'var(--text-secondary)' }}>
                    <Users size={14} strokeWidth={1.5} />
                    {g.student_count} учеников
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-outline" style={{ flex: 1, fontSize: 13, padding: '8px', borderRadius: 10 }}
                  onClick={(e) => { e.stopPropagation(); openManage(g) }}>
                  Управлять
                </button>
                <button style={{
                  width: 38, height: 38, borderRadius: 10,
                  border: '1px solid rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.04)',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                }} onClick={(e) => { e.stopPropagation(); handleDelete(g.id) }}>
                  <Trash2 size={14} color="#dc2626" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}
            style={{ maxWidth: 400, borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: 18, fontWeight: 800 }}>Новая группа</h3>
              <button className="btn btn-sm" onClick={() => setShowCreate(false)}
                style={{ borderRadius: 8, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X size={16} />
              </button>
            </div>
            <div style={{ padding: '12px 20px' }}>
              <input type="text" placeholder="Название группы" value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleCreate()}
                style={{ width: '100%', height: 42, borderRadius: 10, border: '1px solid var(--border)', padding: '0 14px', fontSize: 14, background: '#fff', marginBottom: 14 }} />
              <button className="btn btn-primary" onClick={handleCreate} disabled={!newName.trim()}
                style={{ width: '100%', borderRadius: 12, padding: '10px', opacity: !newName.trim() ? 0.5 : 1 }}>
                Создать
              </button>
            </div>
          </div>
        </div>
      )}

      {manageGroup && (
        <div className="modal-overlay" onClick={() => { setManageGroup(null); setGroupDetail(null) }}>
          <div className="modal" onClick={e => e.stopPropagation()}
            style={{ maxWidth: 560, borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)', maxHeight: '85vh' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: 18, fontWeight: 800 }}>{manageGroup.name}</h3>
              <button className="btn btn-sm" onClick={() => { setManageGroup(null); setGroupDetail(null) }}
                style={{ borderRadius: 8, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X size={16} />
              </button>
            </div>
            <div style={{ padding: '12px 20px', maxHeight: 'calc(85vh - 80px)', overflowY: 'auto' }}>
              <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <div style={{ position: 'relative', flex: 1 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input type="text" placeholder="Поиск ученика..." value={studentSearch}
                      onChange={e => setStudentSearch(e.target.value)}
                      style={{ flex: 1, height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff' }} />
                    <Search size={16} style={{ color: 'var(--text-secondary)', flexShrink: 0 }} />
                  </div>
                  {studentResults.length > 0 && (
                    <div style={{
                      position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100,
                      background: '#fff', border: '1px solid var(--border)', borderRadius: 12,
                      marginTop: 4, maxHeight: 180, overflowY: 'auto', boxShadow: 'var(--shadow-lg)',
                    }}>
                      {studentResults.filter(s => !groupDetail?.student_list?.find(st => st.id === s.id)).map(s => (
                        <div key={s.id}
                          style={{ padding: '10px 14px', cursor: 'pointer', borderBottom: '1px solid #f0f0f0', fontSize: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                          onClick={() => { setStudentSearch(''); addStudent(s) }}>
                          <span>{s.full_name || s.username} <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>@{s.username}</span></span>
                          <span style={{ color: 'var(--primary)', fontWeight: 600, fontSize: 13 }}>+ Добавить</span>
                        </div>
                      ))}
                      {studentResults.filter(s => !groupDetail?.student_list?.find(st => st.id === s.id)).length === 0 && (
                        <div style={{ padding: '12px 14px', fontSize: 13, color: 'var(--text-secondary)' }}>Все найденные уже в группе</div>
                      )}
                    </div>
                  )}
                </div>
                <button style={{
                  width: 38, height: 38, borderRadius: 10,
                  border: '1px solid var(--border)', background: '#fff', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }} onClick={() => setShowCreateStudent(true)} title="Создать ученика">
                  <UserPlus size={16} color="var(--primary)" />
                </button>
              </div>

              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>
                Ученики в группе ({groupDetail?.student_list?.length || 0})
              </div>
              {groupDetail?.student_list?.length === 0 ? (
                <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 14 }}>
                  Пока нет учеников. Найдите через поиск или создайте нового.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {groupDetail?.student_list?.map(st => (
                    <div key={st.id}
                      style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '10px 14px', background: '#fff', borderRadius: 10,
                        border: '1px solid var(--border)',
                      }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{st.full_name || st.username}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>@{st.username}</div>
                      </div>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        {moveTarget === st.id ? (
                          <select defaultValue="" onChange={e => { if (e.target.value) moveStudent(st.id, manageGroup.id, e.target.value) }}
                            onBlur={() => setMoveTarget(null)} autoFocus
                            style={{ height: 32, borderRadius: 8, border: '1px solid var(--border)', padding: '0 8px', fontSize: 13, background: '#fff' }}>
                            <option value="">Переместить в...</option>
                            {groups.filter(g => g.id !== manageGroup.id).map(g => (
                              <option key={g.id} value={g.id}>{g.name}</option>
                            ))}
                          </select>
                        ) : (
                          <button style={{
                            width: 32, height: 32, borderRadius: 8,
                            border: '1px solid rgba(99,102,241,0.2)', background: 'rgba(99,102,241,0.04)',
                            cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          }} onClick={() => setMoveTarget(st.id)} title="Переместить">
                            <ArrowRight size={14} color="var(--primary)" />
                          </button>
                        )}
                        <button style={{
                          width: 32, height: 32, borderRadius: 8,
                          border: '1px solid rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.04)',
                          cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }} onClick={() => removeStudent(st.id)} title="Удалить">
                          <X size={14} color="#dc2626" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {showCreateStudent && (
        <div className="modal-overlay" onClick={() => setShowCreateStudent(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}
            style={{ maxWidth: 400, borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: 18, fontWeight: 800 }}>Новый ученик</h3>
              <button className="btn btn-sm" onClick={() => setShowCreateStudent(false)}
                style={{ borderRadius: 8, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X size={16} />
              </button>
            </div>
            <div style={{ padding: '12px 20px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <input type="text" placeholder="ФИО" value={newStudent.full_name}
                  onChange={e => setNewStudent(prev => ({ ...prev, full_name: e.target.value }))}
                  style={{ width: '100%', height: 42, borderRadius: 10, border: '1px solid var(--border)', padding: '0 14px', fontSize: 14, background: '#fff' }} />
                <input type="text" placeholder="Username (логин)" value={newStudent.username}
                  onChange={e => setNewStudent(prev => ({ ...prev, username: e.target.value }))}
                  style={{ width: '100%', height: 42, borderRadius: 10, border: '1px solid var(--border)', padding: '0 14px', fontSize: 14, background: '#fff' }} />
                <input type="text" placeholder="Пароль" value={newStudent.password}
                  onChange={e => setNewStudent(prev => ({ ...prev, password: e.target.value }))}
                  style={{ width: '100%', height: 42, borderRadius: 10, border: '1px solid var(--border)', padding: '0 14px', fontSize: 14, background: '#fff' }} />
                <button className="btn btn-primary" onClick={handleCreateStudent}
                  disabled={!newStudent.username || !newStudent.password}
                  style={{ width: '100%', borderRadius: 12, padding: '10px', opacity: (!newStudent.username || !newStudent.password) ? 0.5 : 1 }}>
                  Создать и добавить в группу
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
