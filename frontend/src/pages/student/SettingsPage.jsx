import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { authAPI, subjectsAPI } from '../../api'
import { useAuth } from '../../context/AuthContext'
import { ArrowLeft, User, Camera, LogOut, Trash2, BookOpen, BarChart3, Settings, AlertTriangle, Tag, KeyRound, Check, Eye, EyeOff } from 'lucide-react'

export default function SettingsPage() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [allSubjects, setAllSubjects] = useState([])
  const [selectedSubjects, setSelectedSubjects] = useState([])
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPasswords, setShowPasswords] = useState(false)
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordMessage, setPasswordMessage] = useState(null)

  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const fileInputRef = useRef(null)

  const handleAvatarChange = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadingAvatar(true)
    try {
      const res = await authAPI.uploadAvatar(file)
      setProfile(prev => ({ ...prev, avatar: res.data.avatar }))
    } catch (error) {
      alert(error.response?.data?.error || 'Ошибка загрузки аватара')
    } finally {
      setUploadingAvatar(false)
      e.target.value = ''
    }
  }

  useEffect(() => {
    Promise.all([
      authAPI.profile(),
      subjectsAPI.list(),
    ]).then(([prof, subs]) => {
      setProfile(prof.data)
      setAllSubjects(Array.isArray(subs.data) ? subs.data : [])
      setSelectedSubjects(prof.data.profile_subjects || [])
    }).catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const changePassword = async () => {
    setPasswordMessage(null)
    if (newPassword !== confirmPassword) {
      setPasswordMessage({ type: 'error', text: 'Новые пароли не совпадают' })
      return
    }
    setChangingPassword(true)
    try {
      await authAPI.changePassword(oldPassword, newPassword)
      setPasswordMessage({ type: 'success', text: 'Пароль изменён' })
      setOldPassword(''); setNewPassword(''); setConfirmPassword('')
    } catch (error) {
      setPasswordMessage({ type: 'error', text: error.response?.data?.error || 'Ошибка смены пароля' })
    } finally {
      setChangingPassword(false)
    }
  }

  const clearHistory = async () => {
    if (!confirm('Удалить всю историю тестов? Это действие нельзя отменить.')) return
    setDeleting(true)
    try {
      await authAPI.clearHistory()
      setProfile(prev => ({
        ...prev,
        stats: { total_tests: 0, total_questions: 0, correct_answers: 0, avg_score: 0 },
      }))
    } catch (error) {
      alert(error.response?.data?.error || error.response?.data?.detail || JSON.stringify(error.response?.data) || 'Ошибка сервера')
    } finally {
      setDeleting(false)
    }
  }

  const deleteAccount = async () => {
    if (!confirm('Удалить аккаунт и все данные? Это действие нельзя отменить.')) return
    const password = prompt('Введите текущий пароль для удаления аккаунта')
    if (password === null) return
    setDeleting(true)
    try {
      await authAPI.deleteAccount(password)
      logout()
      navigate('/login')
    } catch (error) {
      alert(error.response?.data?.error || 'Не удалось удалить аккаунт')
    } finally {
      setDeleting(false)
    }
  }

  const initials = user?.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.username?.[0]?.toUpperCase() || '?'

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>

  const stats = profile?.stats || {}
  const isStudent = user?.role === 'student'

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      <div className="card" style={{
        display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 16px', marginBottom: 20,
        cursor: 'pointer',
      }} onClick={() => navigate(-1)}>
        <ArrowLeft size={16} strokeWidth={1.5} />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Назад</span>
      </div>

      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, color: 'var(--text)', margin: 0 }}>Настройки</h1>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 4 }}>Управление профилем и данными</p>
      </div>

      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 10, paddingLeft: 4 }}>
        <User size={14} strokeWidth={1.5} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
        Аккаунт
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 28 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 20, marginBottom: 20,
          padding: 20, borderRadius: 'var(--radius)',
          background: 'linear-gradient(135deg, #ffffff 0%, #faf7ef 100%)',
        }}>
          <div style={{ position: 'relative' }}>
            <div style={{
              width: 72, height: 72, borderRadius: '50%', overflow: 'hidden',
              border: '3px solid var(--primary)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 28, fontWeight: 800, color: '#fff',
              background: profile?.avatar ? 'none' : 'var(--primary)',
            }}>
              {profile?.avatar ? (
                <img src={profile.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : initials}
            </div>
            <input type="file" ref={fileInputRef} onChange={handleAvatarChange} accept="image/*" style={{ display: 'none' }} />
            <button onClick={() => !uploadingAvatar && fileInputRef.current?.click()}
              style={{
                position: 'absolute', bottom: 0, right: -2, width: 28, height: 28, borderRadius: '50%',
                background: 'var(--primary)', border: '2px solid #fff', cursor: uploadingAvatar ? 'wait' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
              <Camera size={14} strokeWidth={2} style={{ color: '#fff' }} />
            </button>
          </div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text)' }}>
              {profile?.full_name || profile?.username}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Tag size={12} strokeWidth={1.5} />
              @{profile?.username || 'user'}
            </div>
          </div>
        </div>

        <button onClick={handleLogout}
          style={{
            width: '100%', padding: '12px 20px', borderRadius: 12,
            border: '1px solid rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.04)',
            cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            fontSize: 14, fontWeight: 600, color: '#dc2626',
          }}>
          <LogOut size={16} strokeWidth={1.5} />
          Выйти из аккаунта
        </button>
      </div>

      {isStudent && (
        <>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 10, paddingLeft: 4 }}>
            <BookOpen size={14} strokeWidth={1.5} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
            Мои предметы
          </div>
          <div className="card" style={{ padding: 24, marginBottom: 28 }}>
            <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 16 }}>
              Предметы назначены учителем. Для изменения обратитесь к преподавателю.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {allSubjects.filter(s => selectedSubjects.includes(s.id) || s.subject_type === 'mandatory').map(s => (
                <span key={s.id} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '8px 14px', borderRadius: 10, fontSize: 14, fontWeight: 500,
                  background: s.subject_type === 'mandatory' ? 'rgba(245,158,11,0.08)' : 'rgba(99,102,241,0.06)',
                  color: s.subject_type === 'mandatory' ? '#92400E' : 'var(--primary)',
                  border: '1px solid ' + (s.subject_type === 'mandatory' ? 'rgba(245,158,11,0.2)' : 'rgba(99,102,241,0.15)'),
                }}>
                  <span>{s.icon}</span>
                  {s.name}
                  {s.subject_type === 'mandatory' && <span style={{ fontSize: 10, opacity: 0.6 }}>обяз.</span>}
                </span>
              ))}
            </div>
          </div>
        </>
      )}

      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 10, paddingLeft: 4 }}>
        <KeyRound size={14} strokeWidth={1.5} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
        Безопасность
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 28 }}>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>Смена пароля</div>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
          Используйте пароль длиной не менее 8 символов
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 14 }}>
          {[
            { value: oldPassword, set: setOldPassword, placeholder: 'Текущий пароль' },
            { value: newPassword, set: setNewPassword, placeholder: 'Новый пароль' },
            { value: confirmPassword, set: setConfirmPassword, placeholder: 'Повторите новый пароль' },
          ].map((f, i) => (
            <div key={i} style={{ position: 'relative' }}>
              <input
                type={showPasswords ? 'text' : 'password'}
                value={f.value}
                onChange={e => f.set(e.target.value)}
                placeholder={f.placeholder}
                autoComplete={i === 0 ? 'current-password' : 'new-password'}
                style={{
                  width: '100%', height: 44, borderRadius: 12, border: '1px solid var(--border)',
                  padding: '0 44px 0 14px', fontSize: 14, background: '#fff', outline: 'none',
                }}
              />
              {i === 0 && (
                <button onClick={() => setShowPasswords(v => !v)} type="button"
                  style={{
                    position: 'absolute', right: 8, top: 8, width: 28, height: 28, borderRadius: 8,
                    border: 'none', background: 'transparent', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: 'var(--text-secondary)',
                  }}>
                  {showPasswords ? <EyeOff size={16} strokeWidth={1.5} /> : <Eye size={16} strokeWidth={1.5} />}
                </button>
              )}
            </div>
          ))}
        </div>
        {passwordMessage && (
          <div style={{
            padding: '10px 14px', borderRadius: 10, fontSize: 13, fontWeight: 600, marginBottom: 12,
            background: passwordMessage.type === 'success' ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
            color: passwordMessage.type === 'success' ? '#059669' : '#DC2626',
          }}>
            {passwordMessage.text}
          </div>
        )}
        <button onClick={changePassword} disabled={changingPassword || !oldPassword || !newPassword || !confirmPassword}
          className="btn btn-primary"
          style={{
            width: '100%', borderRadius: 12, padding: '11px',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            opacity: (changingPassword || !oldPassword || !newPassword || !confirmPassword) ? 0.5 : 1,
            cursor: (changingPassword || !oldPassword || !newPassword || !confirmPassword) ? 'not-allowed' : 'pointer',
          }}>
          <Check size={16} strokeWidth={2} />
          {changingPassword ? 'Сохраняем...' : 'Сменить пароль'}
        </button>
      </div>

      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 10, paddingLeft: 4 }}>
        <BarChart3 size={14} strokeWidth={1.5} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
        Статистика
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 28 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {[
            { label: 'Тестов пройдено', value: stats.total_tests ?? 0 },
            { label: 'Вопросов решено', value: stats.total_questions ?? 0 },
            { label: 'Правильных ответов', value: stats.correct_answers ?? 0 },
            { label: 'Процент верных', value: (stats.avg_score ?? 0) + '%' },
          ].map(row => (
            <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
              <span style={{ fontSize: 14, color: 'var(--text-secondary)' }}>{row.label}</span>
              <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>{row.value}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 10, paddingLeft: 4 }}>
        <Settings size={14} strokeWidth={1.5} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
        Опасная зона
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 40, border: '1px solid rgba(239,68,68,0.15)' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <button onClick={clearHistory} disabled={deleting}
            style={{
              display: 'flex', alignItems: 'center', gap: 10, cursor: deleting ? 'wait' : 'pointer',
              padding: '8px 12px', borderRadius: 10, background: 'none', border: 'none',
              font: 'inherit', color: '#dc2626', transition: 'background 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(239,68,68,0.04)'}
            onMouseLeave={e => e.currentTarget.style.background = 'none'}>
            <Trash2 size={16} strokeWidth={1.5} />
            <span style={{ fontSize: 14, fontWeight: 600 }}>
              {deleting ? 'Удаление...' : 'Удалить всю историю тестов'}
            </span>
          </button>
          <button onClick={deleteAccount} disabled={deleting}
            style={{
              display: 'flex', alignItems: 'center', gap: 10, cursor: deleting ? 'wait' : 'pointer',
              padding: '8px 12px', borderRadius: 10, background: 'none', border: 'none',
              font: 'inherit', color: '#dc2626', transition: 'background 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(239,68,68,0.04)'}
            onMouseLeave={e => e.currentTarget.style.background = 'none'}>
            <AlertTriangle size={16} strokeWidth={1.5} />
            <span style={{ fontSize: 14, fontWeight: 600 }}>Удалить аккаунт</span>
          </button>
        </div>
      </div>
    </div>
  )
}
