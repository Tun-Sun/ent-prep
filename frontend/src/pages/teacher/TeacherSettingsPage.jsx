import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { authAPI } from '../../api'
import { useAuth } from '../../context/AuthContext'
import { ArrowLeft, User, Camera, LogOut, Trash2, BarChart3, Settings, AlertTriangle, Tag, Users, FileText, Pencil, Check } from 'lucide-react'

export default function TeacherSettingsPage() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)
  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const [fullName, setFullName] = useState('')
  const [editName, setEditName] = useState(false)
  const [savingName, setSavingName] = useState(false)
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
    authAPI.profile()
      .then(res => { setProfile(res.data); setFullName(res.data.full_name || '') })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const saveFullName = async () => {
    if (!fullName.trim()) return
    setSavingName(true)
    try {
      const res = await authAPI.updateProfile({ full_name: fullName.trim() })
      setProfile(prev => ({ ...prev, full_name: res.data.full_name }))
      setEditName(false)
    } catch (error) {
      alert(error.response?.data?.error || 'Ошибка сохранения')
    } finally {
      setSavingName(false)
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
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
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {editName ? (
                <>
                  <input
                    value={fullName}
                    onChange={e => setFullName(e.target.value)}
                    autoFocus
                    style={{
                      fontSize: 20, fontWeight: 800, color: 'var(--text)',
                      border: 'none', borderBottom: '2px solid var(--primary)',
                      background: 'transparent', outline: 'none',
                      flex: 1, padding: '2px 0', fontFamily: 'inherit',
                    }}
                    placeholder="ФИО"
                  />
                  <button onClick={saveFullName} disabled={savingName || !fullName.trim()}
                    style={{
                      padding: '6px 14px', borderRadius: 8, border: 'none',
                      background: 'var(--primary)', color: '#fff', cursor: 'pointer',
                      fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4,
                      opacity: savingName ? 0.6 : 1,
                    }}>
                    {savingName ? '...' : <><Check size={14} strokeWidth={1.5} /> Сохранить</>}
                  </button>
                </>
              ) : (
                <>
                  <span style={{ fontSize: 20, fontWeight: 800, color: 'var(--text)' }}>
                    {fullName || profile?.username}
                  </span>
                  <button onClick={() => setEditName(true)}
                    style={{
                      padding: 4, borderRadius: 6, border: 'none',
                      background: 'transparent', cursor: 'pointer',
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                    <Pencil size={14} strokeWidth={1.5} style={{ color: 'var(--text-secondary)' }} />
                  </button>
                </>
              )}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Tag size={12} strokeWidth={1.5} />
              @{profile?.username || 'user'}
            </div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--primary)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Users size={12} strokeWidth={1.5} />
              Учитель
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

      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 10, paddingLeft: 4 }}>
        <BarChart3 size={14} strokeWidth={1.5} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
        Статистика
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 28 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {[
            { label: 'Учеников', value: stats.total_students ?? '—', icon: Users },
            { label: 'Тестов проведено', value: stats.total_tests ?? '—', icon: FileText },
            { label: 'Всего вопросов', value: stats.total_questions ?? '—', icon: BarChart3 },
            { label: 'Средний балл учеников', value: stats.avg_score ? stats.avg_score + '%' : '—', icon: BarChart3 },
          ].map(row => (
            <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
              <span style={{ fontSize: 14, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <row.icon size={14} strokeWidth={1.5} style={{ opacity: 0.5 }} />
                {row.label}
              </span>
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
          <button onClick={deleteAccount} disabled={deleting}
            style={{
              display: 'flex', alignItems: 'center', gap: 10, cursor: deleting ? 'wait' : 'pointer',
              padding: '8px 12px', borderRadius: 10, background: 'none', border: 'none',
              font: 'inherit', color: '#dc2626', transition: 'background 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(239,68,68,0.04)'}
            onMouseLeave={e => e.currentTarget.style.background = 'none'}>
            <AlertTriangle size={16} strokeWidth={1.5} />
            <span style={{ fontSize: 14, fontWeight: 600 }}>{deleting ? 'Удаление...' : 'Удалить аккаунт'}</span>
          </button>
        </div>
      </div>
    </div>
  )
}
