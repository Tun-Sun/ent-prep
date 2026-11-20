import { useState, useEffect } from 'react'
import { subjectsAPI, questionsAPI } from '../../api'
import { Users, BookOpen, FolderOpen, Settings, CalendarDays } from 'lucide-react'

const iconSize = 18
const TABS = [
  { key: 'users', label: 'Пользователи', icon: <Users size={iconSize} strokeWidth={1.5} /> },
  { key: 'subjects', label: 'Предметы', icon: <BookOpen size={iconSize} strokeWidth={1.5} /> },
  { key: 'trials', label: 'Пробные', icon: <CalendarDays size={iconSize} strokeWidth={1.5} /> },
  { key: 'topics', label: 'Темы', icon: <FolderOpen size={iconSize} strokeWidth={1.5} /> },
  { key: 'settings', label: 'Настройки', icon: <Settings size={iconSize} strokeWidth={1.5} /> },
]

const ROLE_LABELS = { student: 'Ученик', teacher: 'Учитель', admin: 'Админ' }
const ROLE_COLORS = { student: '#10B981', teacher: '#4F46E5', admin: '#EF4444' }

// datetime-local работает в местном времени браузера, API — в UTC.
const dateToInput = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
const inputToDate = (value) => value ? new Date(value).toISOString() : null

export default function AdminPanelPage() {
  const [tab, setTab] = useState('users')
  return (
    <div style={{ maxWidth: 'none' }}>
      <div className="page-header">
        <h1 className="page-title">Панель администратора</h1>
        <p className="page-subtitle">Управление пользователями, предметами, темами и настройками</p>
      </div>
      <div className="tabs" style={{ marginBottom: 24 }}>
        {TABS.map(t => (
          <button
            key={t.key}
            className={`tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >{t.icon} {t.label}</button>
        ))}
      </div>
      {tab === 'users' && <UsersTab />}
      {tab === 'subjects' && <SubjectsTab />}
      {tab === 'trials' && <TrialScheduleTab />}
      {tab === 'topics' && <TopicsTab />}
      {tab === 'settings' && <SettingsTab />}
    </div>
  )
}

function UsersTab() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('active')
  const [saving, setSaving] = useState(null)
  const [nameUser, setNameUser] = useState(null)
  const [nameDraft, setNameDraft] = useState('')

  const authHeaders = { Authorization: `Bearer ${localStorage.getItem('access_token')}` }

  const load = () => {
    setLoading(true)
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    if (roleFilter) params.set('role', roleFilter)
    if (statusFilter) params.set('status', statusFilter)
    fetch(`/api/auth/admin/users/?${params}`, { headers: authHeaders })
      .then(r => r.json())
      .then(setUsers)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [search, roleFilter, statusFilter])

  const updateUser = (id, data) => {
    setSaving(id)
    fetch(`/api/auth/admin/users/${id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
      body: JSON.stringify(data),
    }).then(r => r.ok ? load() : null).finally(() => setSaving(null))
  }

  const saveName = async () => {
    if (!nameUser || !nameDraft.trim()) return
    try {
      const res = await fetch(`/api/auth/admin/users/${nameUser.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        body: JSON.stringify({ full_name: nameDraft.trim() }),
      })
      if (!res.ok) throw new Error(await res.text())
      setNameUser(null)
      load()
    } catch {
      alert('Не удалось изменить ФИО')
    }
  }

  const deleteUser = (id, name) => {
    if (!confirm(`Удалить пользователя ${name}?`)) return
    fetch(`/api/auth/admin/users/${id}/delete/`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
    }).then(r => r.ok ? load() : alert('Ошибка удаления'))
  }

  return (
    <div className="card">
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <input className="form-input" style={{ maxWidth: 300 }}
          placeholder="Поиск по имени, логину или email..."
          value={search} onChange={e => setSearch(e.target.value)} />
        <select className="form-select" style={{ maxWidth: 160 }}
          value={roleFilter} onChange={e => setRoleFilter(e.target.value)}>
          <option value="">Все роли</option>
          <option value="student">Ученики</option>
          <option value="teacher">Учителя</option>
          <option value="admin">Админы</option>
        </select>
        <select className="form-select" style={{ maxWidth: 180 }}
          value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="active">Активные</option>
          <option value="inactive">Деактивированные</option>
          <option value="all">Все статусы</option>
        </select>
      </div>
      {loading ? <div className="text-center"><div className="spinner"></div></div> : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Логин</th>
                <th>Имя</th>
                <th>Email</th>
                <th>Роль</th>
                <th>Статус</th>
                <th>Дата рег.</th>
                <th>Последний вход</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
                  <td style={{ color: 'var(--text-secondary)' }}>{u.id}</td>
                  <td style={{ fontWeight: 600 }}>{u.username}</td>
                  <td>{u.full_name || '—'}</td>
                  <td>{u.email || '—'}</td>
                  <td>
                    <select className="form-select" style={{ padding: '4px 8px', fontSize: 13, minWidth: 110 }}
                      value={u.role} disabled={saving === u.id}
                      onChange={e => updateUser(u.id, { role: e.target.value })}>
                      <option value="student">Ученик</option>
                      <option value="teacher">Учитель</option>
                      <option value="admin">Админ</option>
                    </select>
                  </td>
                  <td>
                    <span className={`badge badge-${u.is_active ? 'easy' : 'hard'}`}
                      style={{ cursor: 'pointer' }}
                      onClick={() => updateUser(u.id, { is_active: !u.is_active })}>
                      {u.is_active ? 'Активен' : 'Заблокирован'}
                    </span>
                  </td>
                  <td style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    {new Date(u.date_joined).toLocaleDateString('ru-RU')}
                  </td>
                  <td style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    {u.last_login ? new Date(u.last_login).toLocaleDateString('ru-RU') : '—'}
                  </td>
                  <td>
                    <button className="btn btn-sm btn-outline" style={{ marginRight: 6 }}
                      onClick={() => { setNameUser(u); setNameDraft(u.full_name || '') }}>
                      ФИО
                    </button>
                    <button className="btn btn-sm btn-outline" style={{ color: 'var(--danger)' }}
                      onClick={() => deleteUser(u.id, u.full_name || u.username)}>
                      Удалить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {nameUser && (
        <div className="modal-overlay" onClick={() => setNameUser(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}
            style={{ maxWidth: 420, borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: 18, fontWeight: 800 }}>Изменить ФИО</h3>
              <button className="btn btn-sm" onClick={() => setNameUser(null)}>✕</button>
            </div>
            <div style={{ padding: '12px 20px' }}>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 12 }}>
                Логин: {nameUser.username}
              </p>
              <input className="form-input" value={nameDraft}
                onChange={e => setNameDraft(e.target.value)}
                placeholder="Фамилия и имя"
                onKeyDown={e => { if (e.key === 'Enter') saveName() }}
                style={{ width: '100%', marginBottom: 16 }} />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button className="btn btn-outline" onClick={() => setNameUser(null)}>Отмена</button>
                <button className="btn btn-primary" onClick={saveName} disabled={!nameDraft.trim()}>
                  Сохранить
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Пробные варианты живут отдельными предметами. Даты открытия/закрытия —
// единственное, что тренеру нужно менять перед каждым пробником, поэтому
// выносим их в отдельную вкладку, а не в общий список предметов.
const TRIAL_SLUGS = ['ent-01', 'ent-02', 'ent-03', 'nuet-01', 'nuet-02', 'nuet-03']
const TRIAL_TRACKS = { ent: 'ЕНТ', nuet: 'NUET' }

function trialScheduleState(row) {
  if (!row.is_visible) return { label: 'Скрыт', cls: 'badge-hard' }
  const now = Date.now()
  if (row.available_from && now < new Date(row.available_from).getTime()) {
    return { label: 'Откроется позже', cls: 'badge-medium' }
  }
  if (row.available_until && now > new Date(row.available_until).getTime()) {
    return { label: 'Закрыт', cls: 'badge-hard' }
  }
  return { label: 'Доступен', cls: 'badge-easy' }
}

function TrialScheduleTab() {
  const [rows, setRows] = useState([])
  const [drafts, setDrafts] = useState({})
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)
  const [savedId, setSavedId] = useState(null)

  const applyRows = (subjects) => {
    const trials = TRIAL_SLUGS
      .map(slug => subjects.find(s => s.slug === slug))
      .filter(Boolean)
    setRows(trials)
    const next = {}
    trials.forEach(s => {
      next[s.id] = {
        available_from: dateToInput(s.available_from),
        available_until: dateToInput(s.available_until),
        is_visible: s.is_visible,
      }
    })
    setDrafts(next)
  }

  const load = () => subjectsAPI.list()
    .then(res => applyRows(Array.isArray(res.data) ? res.data : []))
    .catch(() => {})
    .finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  const updateDraft = (id, patch) =>
    setDrafts(prev => ({ ...prev, [id]: { ...prev[id], ...patch } }))

  const save = async (row, override = {}) => {
    const draft = { ...drafts[row.id], ...override }
    setSavingId(row.id)
    setSavedId(null)
    try {
      const res = await fetch(`/api/subjects/${row.id}/`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
        body: JSON.stringify({
          available_from: inputToDate(draft.available_from),
          available_until: inputToDate(draft.available_until),
          is_visible: draft.is_visible,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      setSavedId(row.id)
      await load()
    } catch {
      alert('Не удалось сохранить расписание')
    } finally {
      setSavingId(null)
    }
  }

  if (loading) return <div className="text-center"><div className="spinner"></div></div>

  return (
    <div className="card">
      <div style={{ marginBottom: 18 }}>
        <h3 style={{ fontSize: 18, fontWeight: 800, marginBottom: 6 }}>Расписание пробных вариантов</h3>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
          Пустое поле — без ограничения. Вне окна вариант не показывается ученику
          в каталоге и не запускается. Время — местное (Алматы).
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {rows.map(row => {
          const draft = drafts[row.id] || {}
          const state = trialScheduleState({ ...row, ...draft })
          return (
            <div key={row.id} style={{
              border: '1px solid var(--border)', borderRadius: 12, padding: '14px 16px',
              background: '#fff', display: 'flex', flexWrap: 'wrap', gap: 14, alignItems: 'flex-end',
            }}>
              <div style={{ flex: '1 1 200px', minWidth: 180 }}>
                <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{row.name}</div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                  <span className="badge" style={{ fontSize: 10 }}>{TRIAL_TRACKS[row.track] || row.track}</span>
                  <span className="badge" style={{ fontSize: 10 }}>{row.question_count} вопросов</span>
                  <span className={`badge ${state.cls}`} style={{ fontSize: 10 }}>{state.label}</span>
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Открыт с
                </label>
                <input className="form-input" type="datetime-local"
                  value={draft.available_from || ''}
                  onChange={e => updateDraft(row.id, { available_from: e.target.value })}
                  style={{ minWidth: 190 }} />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Закрыт до
                </label>
                <input className="form-input" type="datetime-local"
                  value={draft.available_until || ''}
                  onChange={e => updateDraft(row.id, { available_until: e.target.value })}
                  style={{ minWidth: 190 }} />
              </div>

              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <button className="btn btn-primary btn-sm" onClick={() => save(row)}
                  disabled={savingId === row.id}>
                  {savingId === row.id ? 'Сохраняем…' : savedId === row.id ? 'Сохранено ✓' : 'Сохранить'}
                </button>
                <button className="btn btn-outline btn-sm"
                  onClick={() => {
                    updateDraft(row.id, { available_from: '', available_until: '' })
                    save(row, { available_from: '', available_until: '' })
                  }}
                  title="Убрать обе даты — вариант доступен всегда">
                  Бессрочно
                </button>
                <button className={row.is_visible ? 'btn btn-outline btn-sm' : 'btn btn-success btn-sm'}
                  onClick={() => save(row, { is_visible: !draft.is_visible })}
                  disabled={savingId === row.id}>
                  {row.is_visible ? 'Скрыть' : 'Показать'}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SubjectsTab() {
  const [subjects, setSubjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState(null)
  const [pressedId, setPressedId] = useState(null)
  const [form, setForm] = useState({ name: '', slug: '', icon: '📚', description: '', subject_type: 'profile', sort_order: 0, is_visible: true, question_count: 10, time_limit: 600, show_in_profiles: true, available_from: '', available_until: '' })

  const SUBJECT_COLORS = ['#4F46E5','#10B981','#F59E0B','#EF4444','#8B5CF6','#EC4899','#14B8A6','#F97316','#06B6D4','#84CC16','#6366F1','#D946EF','#0EA5E9']
  const colorMap = {}
  subjects.forEach((s, i) => { colorMap[s.id] = SUBJECT_COLORS[i % SUBJECT_COLORS.length] })

  const load = () => subjectsAPI.list().then(r => setSubjects(r.data)).catch(() => {}).finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEditId(null)
    setForm({ name: '', slug: '', icon: '📚', description: '', subject_type: 'profile', sort_order: 0, is_visible: true, show_in_profiles: true, available_from: '', available_until: '' })
    setShowForm(true)
  }

  const openEdit = (s) => {
    setEditId(s.id)
    setForm({ name: s.name, slug: s.slug, icon: s.icon, description: s.description, subject_type: s.subject_type, sort_order: s.sort_order, is_visible: s.is_visible, question_count: s.question_count ?? 10, time_limit: s.time_limit ?? 600, show_in_profiles: s.show_in_profiles ?? true, available_from: dateToInput(s.available_from), available_until: dateToInput(s.available_until) })
    setShowForm(true)
  }

  const save = async () => {
    const method = editId ? 'PUT' : 'POST'
    const url = editId ? `/api/subjects/${editId}/` : '/api/subjects/'
    try {
      await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        body: JSON.stringify({
          ...form,
          available_from: inputToDate(form.available_from),
          available_until: inputToDate(form.available_until),
        }),
      })
      setShowForm(false)
      load()
    } catch { alert('Ошибка сохранения') }
  }

  const remove = (id) => {
    if (!confirm('Удалить предмет?')) return
    fetch(`/api/subjects/${id}/`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
    }).then(r => r.ok ? load() : alert('Ошибка'))
  }

  const [selectedIds, setSelectedIds] = useState([])

  const toggleProfileVisibility = async (show) => {
    if (selectedIds.length === 0) return
    try {
      await Promise.all(selectedIds.map(id =>
        fetch(`/api/subjects/${id}/`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
          body: JSON.stringify({ show_in_profiles: show }),
        })
      ))
      setSelectedIds([])
      load()
    } catch { alert('Ошибка') }
  }

  const toggleSingleProfileShow = (id, current) => {
    fetch(`/api/subjects/${id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
      body: JSON.stringify({ show_in_profiles: !current }),
    }).then(r => r.ok ? load() : r.text().then(t => alert('Ошибка: ' + t)))
  }

  const toggleSubjectVisibility = (id, current) => {
    fetch(`/api/subjects/${id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
      body: JSON.stringify({ is_visible: !current }),
    }).then(r => r.ok ? load() : r.text().then(t => alert('Ошибка: ' + t)))
  }

  const TYPE_LABELS = { mandatory: 'Обязательный', profile: 'Профильный', other: 'Дополнительный' }

  if (loading) return <div className="text-center"><div className="spinner"></div></div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <button className="btn btn-primary" onClick={openCreate}>+ Создать предмет</button>
      </div>
      <div className="subj-section-list">
        {subjects.map(s => {
          const color = colorMap[s.id] || 'var(--primary)'
          const isPressed = pressedId === s.id
          return (
            <div key={s.id} className="subject-row"
              style={{
                '--subject-color': color,
                boxShadow: isPressed ? `0 1px 0 0 var(--border)` : `0 3px 0 0 var(--border)`,
                transform: isPressed ? 'translateY(2px)' : 'none',
              }}>
              {s.subject_type === 'profile' && (
                <input type="checkbox" checked={selectedIds.includes(s.id)}
                  onChange={e => setSelectedIds(prev =>
                    e.target.checked ? [...prev, s.id] : prev.filter(id => id !== s.id)
                  )}
                  style={{ marginLeft: 12, width: 18, height: 18, cursor: 'pointer', flexShrink: 0 }} />
              )}
              <div className="subject-row-border" style={{ background: color }} />
              <span className="subject-row-icon">{s.icon}</span>
              <div className="subject-row-info">
                <div className="subject-row-name">{s.name}</div>
                <div className="subject-row-meta">
                  {s.question_count} вопросов · {s.topic_count} тем
                  {(s.available_from || s.available_until) && (
                    <span className="badge" style={{ marginLeft: 6, fontSize: 9 }}>по расписанию</span>
                  )}
                  <span className={`badge ${s.is_visible ? 'badge-easy' : 'badge-hard'}`}
                    style={{ marginLeft: 8, cursor: 'pointer', fontSize: 9 }}
                    onClick={e => { e.stopPropagation(); toggleSubjectVisibility(s.id, s.is_visible) }}>
                    {s.is_visible ? 'Виден' : 'Скрыт'}
                  </span>
                  {s.subject_type === 'profile' && (
                    <span className={`badge ${s.show_in_profiles ? 'badge-easy' : 'badge-hard'}`}
                      style={{ marginLeft: 4, fontSize: 9, cursor: 'pointer' }}
                      onClick={e => { e.stopPropagation(); toggleSingleProfileShow(s.id, s.show_in_profiles) }}>
                      {s.show_in_profiles ? 'В профилях' : 'Скрыт'}
                    </span>
                  )}
                  <span className="badge" style={{ marginLeft: 4, fontSize: 9 }}>{TYPE_LABELS[s.subject_type]}</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 4, paddingRight: 12, flexShrink: 0 }}>
                <button className="btn btn-sm" onClick={() => openEdit(s)}>✏️</button>
                <button className="btn btn-sm" style={{ color: 'var(--danger)' }} onClick={() => remove(s.id)}>🗑️</button>
              </div>
            </div>
          )
        })}
      </div>
      {selectedIds.length > 0 && (
        <div style={{ display: 'flex', gap: 10, marginTop: 16, justifyContent: 'center' }}>
          <button className="btn btn-success" onClick={() => toggleProfileVisibility(true)}>
            Показать в профилях ({selectedIds.length})
          </button>
          <button className="btn btn-danger" onClick={() => toggleProfileVisibility(false)}>
            Скрыть в профилях ({selectedIds.length})
          </button>
        </div>
      )}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editId ? 'Редактировать' : 'Создать'} предмет</h3>
              <button className="btn btn-sm" onClick={() => setShowForm(false)}>✕</button>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <input className="form-input" placeholder="Название" value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value, slug: editId ? f.slug : e.target.value.toLowerCase().replace(/[^a-zа-яё0-9]+/g, '-').replace(/^-|-$/g, '') }))} />
              <input className="form-input" placeholder="Slug" value={form.slug}
                onChange={e => setForm(f => ({ ...f, slug: e.target.value }))} />
              <input className="form-input" placeholder="Иконка (эмодзи)" value={form.icon}
                onChange={e => setForm(f => ({ ...f, icon: e.target.value }))} />
              <textarea className="form-input" placeholder="Описание" rows={3} value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
              <select className="form-select" value={form.subject_type}
                onChange={e => setForm(f => ({ ...f, subject_type: e.target.value }))}>
                <option value="mandatory">Обязательный (ЕНТ)</option>
                <option value="profile">Профильный (ЕНТ)</option>
                <option value="other">Дополнительный</option>
              </select>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input type="checkbox" checked={form.is_visible}
                  onChange={e => setForm(f => ({ ...f, is_visible: e.target.checked }))} />
                Виден ученикам
              </label>
              <label className="form-label" style={{ marginTop: 8 }}>Доступен с (пусто — всегда)</label>
              <input className="form-input" type="datetime-local" value={form.available_from}
                onChange={e => setForm(f => ({ ...f, available_from: e.target.value }))} />
              <label className="form-label">Доступен до (пусто — всегда)</label>
              <input className="form-input" type="datetime-local" value={form.available_until}
                onChange={e => setForm(f => ({ ...f, available_until: e.target.value }))} />
              <input className="form-input" type="number" placeholder="Кол-во вопросов" value={form.question_count}
                onChange={e => setForm(f => ({ ...f, question_count: parseInt(e.target.value) || 10 }))} />
              <input className="form-input" type="number" placeholder="Лимит времени (сек)" value={form.time_limit}
                onChange={e => setForm(f => ({ ...f, time_limit: parseInt(e.target.value) || 600 }))} />
            </div>
            <div className="modal-footer">
              <button className="btn btn-outline" onClick={() => setShowForm(false)}>Отмена</button>
              <button className="btn btn-primary" onClick={save}>{editId ? 'Сохранить' : 'Создать'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function TopicsTab() {
  const [topics, setTopics] = useState([])
  const [subjects, setSubjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [filterSubject, setFilterSubject] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState({ name: '', subject: '' })
  const [pressedId, setPressedId] = useState(null)

  const SUBJECT_COLORS = ['#4F46E5','#10B981','#F59E0B','#EF4444','#8B5CF6','#EC4899','#14B8A6','#F97316','#06B6D4','#84CC16','#6366F1','#D946EF','#0EA5E9']
  const colorMap = {}
  subjects.forEach((s, i) => { colorMap[s.id] = SUBJECT_COLORS[i % SUBJECT_COLORS.length] })

  const load = () => {
    setLoading(true)
    const params = filterSubject ? `?subject=${filterSubject}` : ''
    fetch(`/api/topics/${params}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
    })
      .then(r => r.json())
      .then(setTopics)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    subjectsAPI.list().then(r => setSubjects(r.data))
  }, [])

  useEffect(() => { load() }, [filterSubject])

  const openCreate = () => {
    setEditId(null)
    setForm({ name: '', subject: filterSubject || (subjects[0]?.id || '') })
    setShowForm(true)
  }

  const openEdit = (t) => {
    setEditId(t.id)
    setForm({ name: t.name, subject: t.subject })
    setShowForm(true)
  }

  const save = async () => {
    const method = editId ? 'PUT' : 'POST'
    const url = editId ? `/api/topics/${editId}/` : '/api/topics/'
    try {
      await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        body: JSON.stringify(form),
      })
      setShowForm(false)
      load()
    } catch { alert('Ошибка сохранения') }
  }

  const remove = (id) => {
    if (!confirm('Удалить тему?')) return
    fetch(`/api/topics/${id}/`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
    }).then(r => r.ok ? load() : alert('Ошибка'))
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center' }}>
        <select className="form-select" style={{ maxWidth: 250 }}
          value={filterSubject} onChange={e => setFilterSubject(e.target.value)}>
          <option value="">Все предметы</option>
          {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
        </select>
        <button className="btn btn-primary" onClick={openCreate}>+ Создать тему</button>
      </div>
      {loading ? <div className="text-center"><div className="spinner"></div></div> : (
        <div className="subj-section-list">
          {topics.map(t => {
            const color = colorMap[t.subject] || 'var(--primary)'
            const isPressed = pressedId === t.id
            return (
              <div key={t.id} className="subject-row"
                style={{
                  '--subject-color': color,
                  boxShadow: isPressed ? `0 1px 0 0 var(--border)` : `0 3px 0 0 var(--border)`,
                  transform: isPressed ? 'translateY(2px)' : 'none',
                }}>
                <div className="subject-row-border" style={{ background: color }} />
                <div className="subject-row-info" style={{ padding: '14px 0', marginLeft: 14 }}>
                  <div className="subject-row-name">{t.name}</div>
                  <div className="subject-row-meta">{t.subject_name}</div>
                </div>
                <div style={{ display: 'flex', gap: 4, paddingRight: 12, flexShrink: 0 }}>
                  <button className="btn btn-sm" onClick={() => openEdit(t)}>✏️</button>
                  <button className="btn btn-sm" style={{ color: 'var(--danger)' }} onClick={() => remove(t.id)}>🗑️</button>
                </div>
              </div>
            )
          })}
          {topics.length === 0 && <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: 32 }}>Нет тем</p>}
        </div>
      )}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editId ? 'Редактировать' : 'Создать'} тему</h3>
              <button className="btn btn-sm" onClick={() => setShowForm(false)}>✕</button>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <input className="form-input" placeholder="Название темы" value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
              <select className="form-select" value={form.subject}
                onChange={e => setForm(f => ({ ...f, subject: e.target.value }))}>
                <option value="">— выберите предмет —</option>
                {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
              </select>
            </div>
            <div className="modal-footer">
              <button className="btn btn-outline" onClick={() => setShowForm(false)}>Отмена</button>
              <button className="btn btn-primary" onClick={save}>{editId ? 'Сохранить' : 'Создать'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function SettingsTab() {
  const [settings, setSettings] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(null)

  const load = () => {
    setLoading(true)
    fetch('/api/auth/admin/settings/', {
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
    }).then(r => r.json()).then(setSettings).catch(() => {}).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const update = (id, value) => {
    setSaving(id)
    fetch(`/api/auth/admin/settings/${id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
      body: JSON.stringify({ value }),
    }).then(r => r.ok ? load() : null).finally(() => setSaving(null))
  }

  const addSetting = async () => {
    const key = prompt('Ключ настройки (англ., без пробелов):')
    if (!key) return
    await fetch('/api/auth/admin/settings/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
      body: JSON.stringify({ key, value: '', description: '' }),
    })
    load()
  }

  if (loading) return <div className="text-center"><div className="spinner"></div></div>

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <p className="page-subtitle" style={{ margin: 0 }}>Системные настройки (ключ — значение)</p>
        <button className="btn btn-primary btn-sm" onClick={addSetting}>+ Добавить</button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {settings.map(s => (
          <div key={s.id} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
            <div style={{ minWidth: 180, fontWeight: 600, fontSize: 14 }}>
              {s.key}
              {s.description && <div style={{ fontWeight: 400, fontSize: 12, color: 'var(--text-secondary)' }}>{s.description}</div>}
            </div>
            <input className="form-input"
              value={s.value}
              disabled={saving === s.id}
              onChange={e => update(s.id, e.target.value)}
              onBlur={e => {
                if (e.target.value !== s.value) update(s.id, e.target.value)
              }} />
          </div>
        ))}
        {settings.length === 0 && <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: 32 }}>Нет настроек. Нажмите «+ Добавить»</p>}
      </div>
    </div>
  )
}
