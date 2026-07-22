import { useState, useEffect } from 'react'
import { groupsAPI } from '../../api'
import { Plus, X, Search, Users, Trash2, Layers, UserPlus, ArrowRight } from 'lucide-react'

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

  const modalOverlay = { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }
  const modalContent = { background: '#F4EEDC', border: '2px solid #1B1B1B', borderRadius: 26, padding: 28, width: '100%', maxWidth: 520, maxHeight: '80vh', overflowY: 'auto', boxShadow: '6px 6px 0 0 rgba(0,0,0,0.1)' }

  return (
    <div className="dashboard">
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24, justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ width: 48, height: 48, borderRadius: 16, background: '#111', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, border: '2px solid #1B1B1B', boxShadow: '0 3px 0 0 var(--primary)' }}>
            <Layers size={24} />
          </div>
          <h1 style={{ fontSize: 32, fontWeight: 800, color: 'var(--text)', margin: 0 }}>Группы</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Plus size={16} /> Создать группу
        </button>
      </div>

      {loading ? (
        <div className="text-center mt-8"><div className="spinner"></div></div>
      ) : groups.length === 0 ? (
        <div className="d-card" style={{ padding: 60, textAlign: 'center' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📚</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>Нет групп</div>
          <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 20 }}>Создайте первую группу, чтобы объединять учеников</div>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <Plus size={16} style={{ marginRight: 6 }} /> Создать группу
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
          {groups.map(g => (
            <div key={g.id} className="d-card" style={{ padding: 20, cursor: 'pointer' }}
              onClick={() => openManage(g)}>
              <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>{g.name}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 14, color: 'var(--text-secondary)' }}>
                <Users size={16} /> {g.student_count} учеников
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button className="btn btn-outline" style={{ flex: 1, fontSize: 13, padding: '8px 0' }}
                  onClick={(e) => { e.stopPropagation(); openManage(g) }}>
                  Управлять
                </button>
                <button style={{ width: 36, height: 36, borderRadius: 10, border: '1.5px solid #FF5A4E', background: '#FFF1F1', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                  onClick={(e) => { e.stopPropagation(); handleDelete(g.id) }}>
                  <Trash2 size={14} color="#FF5A4E" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create group modal */}
      {showCreate && (
        <div style={modalOverlay} onClick={() => setShowCreate(false)}>
          <div style={modalContent} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div style={{ fontSize: 20, fontWeight: 700 }}>Новая группа</div>
              <X size={20} style={{ cursor: 'pointer' }} onClick={() => setShowCreate(false)} />
            </div>
            <input type="text" placeholder="Название группы" value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              style={{ width: '100%', height: 44, borderRadius: 14, border: '2px solid #1B1B1B', padding: '0 14px', fontSize: 15, background: '#fff', marginBottom: 14 }} />
            <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleCreate} disabled={!newName.trim()}>
              Создать
            </button>
          </div>
        </div>
      )}

      {/* Manage group modal */}
      {manageGroup && (
        <div style={modalOverlay} onClick={() => { setManageGroup(null); setGroupDetail(null) }}>
          <div style={modalContent} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div style={{ fontSize: 20, fontWeight: 700 }}>{manageGroup.name}</div>
              <X size={20} style={{ cursor: 'pointer' }} onClick={() => { setManageGroup(null); setGroupDetail(null) }} />
            </div>

            {/* Search existing students + create new */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <div style={{ position: 'relative', flex: 1 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input type="text" placeholder="Поиск ученика..." value={studentSearch}
                    onChange={e => setStudentSearch(e.target.value)}
                    style={{ flex: 1, height: 40, borderRadius: 12, border: '1.5px solid var(--border)', padding: '0 12px', fontSize: 14, background: '#fff' }} />
                  <Search size={18} style={{ color: 'var(--text-secondary)' }} />
                </div>
                {studentResults.length > 0 && (
                  <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100, background: '#fff', border: '2px solid #1B1B1B', borderRadius: 12, marginTop: 4, maxHeight: 180, overflowY: 'auto', boxShadow: '3px 3px 0 0 rgba(0,0,0,0.08)' }}>
                    {studentResults.filter(s => !groupDetail?.student_list?.find(st => st.id === s.id)).map(s => (
                      <div key={s.id} style={{ padding: '10px 14px', cursor: 'pointer', borderBottom: '1px solid #f0f0f0', fontSize: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                        onClick={() => { setStudentSearch(''); addStudent(s) }}>
                        <span>{s.full_name || s.username} <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>@{s.username}</span></span>
                        <span style={{ color: '#4F46E5', fontWeight: 600, fontSize: 13 }}>+ Добавить</span>
                      </div>
                    ))}
                    {studentResults.filter(s => !groupDetail?.student_list?.find(st => st.id === s.id)).length === 0 && (
                      <div style={{ padding: '12px 14px', fontSize: 13, color: 'var(--text-secondary)' }}>Все найденные уже в группе</div>
                    )}
                  </div>
                )}
              </div>
              <button style={{ width: 40, height: 40, borderRadius: 12, border: '1.5px solid var(--primary)', background: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
                onClick={() => setShowCreateStudent(true)} title="Создать ученика">
                <UserPlus size={18} color="var(--primary)" />
              </button>
            </div>

            {/* Student list */}
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>
              Ученики в группе ({groupDetail?.student_list?.length || 0})
            </div>
            {groupDetail?.student_list?.length === 0 ? (
              <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 14 }}>
                Пока нет учеников. Найдите через поиск или создайте нового.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {groupDetail?.student_list?.map(st => (
                  <div key={st.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: '#fff', borderRadius: 12, border: '1px solid var(--border)' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 600 }}>{st.full_name || st.username}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>@{st.username}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      {moveTarget === st.id ? (
                        <select defaultValue="" onChange={e => { if (e.target.value) moveStudent(st.id, manageGroup.id, e.target.value) }}
                          onBlur={() => setMoveTarget(null)}
                          autoFocus
                          style={{ height: 32, borderRadius: 8, border: '1.5px solid var(--border)', padding: '0 8px', fontSize: 13, background: '#fff' }}>
                          <option value="">Переместить в...</option>
                          {groups.filter(g => g.id !== manageGroup.id).map(g => (
                            <option key={g.id} value={g.id}>{g.name}</option>
                          ))}
                        </select>
                      ) : (
                        <button style={{ width: 32, height: 32, borderRadius: 8, border: '1.5px solid #4F46E5', background: '#EEF2FF', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                          onClick={() => setMoveTarget(st.id)} title="Переместить в другую группу">
                          <ArrowRight size={14} color="#4F46E5" />
                        </button>
                      )}
                      <button style={{ width: 32, height: 32, borderRadius: 8, border: '1.5px solid #FF5A4E', background: '#FFF1F1', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                        onClick={() => removeStudent(st.id)} title="Удалить из группы">
                        <X size={14} color="#FF5A4E" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create student modal */}
      {showCreateStudent && (
        <div style={modalOverlay} onClick={() => setShowCreateStudent(false)}>
          <div style={modalContent} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div style={{ fontSize: 20, fontWeight: 700 }}>Новый ученик</div>
              <X size={20} style={{ cursor: 'pointer' }} onClick={() => setShowCreateStudent(false)} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <input type="text" placeholder="ФИО" value={newStudent.full_name}
                onChange={e => setNewStudent(prev => ({ ...prev, full_name: e.target.value }))}
                style={{ width: '100%', height: 44, borderRadius: 14, border: '2px solid #1B1B1B', padding: '0 14px', fontSize: 15, background: '#fff' }} />
              <input type="text" placeholder="Username (логин)" value={newStudent.username}
                onChange={e => setNewStudent(prev => ({ ...prev, username: e.target.value }))}
                style={{ width: '100%', height: 44, borderRadius: 14, border: '2px solid #1B1B1B', padding: '0 14px', fontSize: 15, background: '#fff' }} />
              <input type="text" placeholder="Пароль" value={newStudent.password}
                onChange={e => setNewStudent(prev => ({ ...prev, password: e.target.value }))}
                style={{ width: '100%', height: 44, borderRadius: 14, border: '2px solid #1B1B1B', padding: '0 14px', fontSize: 15, background: '#fff' }} />
              <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleCreateStudent}
                disabled={!newStudent.username || !newStudent.password}>
                Создать и добавить в группу
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}