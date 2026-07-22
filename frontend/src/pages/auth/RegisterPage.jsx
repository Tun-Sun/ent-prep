import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { subjectsAPI } from '../../api'

export default function RegisterPage() {
  const [form, setForm] = useState({
    username: '', email: '', password: '', password_confirm: '',
    full_name: '', school: '', role: 'student',
  })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [subjects, setSubjects] = useState([])
  const [profileSubjects, setProfileSubjects] = useState([])
  const { register } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    subjectsAPI.forRegistration().then(res => {
      setSubjects(Array.isArray(res.data) ? res.data : [])
    }).catch(() => {})
  }, [])

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value })
  }

  const toggleSubject = (id) => {
    setProfileSubjects(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrors({})
    if (profileSubjects.length === 0) {
      setErrors({ profile_subjects: 'Выберите хотя бы один предмет' })
      return
    }
    setLoading(true)
    try {
      // Публичная регистрация — только ученики (учителей создаёт админ)
      await register({ ...form, role: 'student', profile_subjects: profileSubjects })
      navigate('/')
    } catch (err) {
      const data = err.response?.data
      if (data) {
        const errs = {}
        Object.keys(data).forEach(k => { errs[k] = Array.isArray(data[k]) ? data[k][0] : data[k] })
        setErrors(errs)
      } else {
        setErrors({ general: 'Ошибка регистрации' })
      }
    } finally {
      setLoading(false)
    }
  }

  const mandatorySubjects = subjects.filter(s => s.subject_type === 'mandatory')
  const profileSubjList = subjects.filter(s => s.subject_type === 'profile' && s.show_in_profiles !== false)

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo"><img src="/assets/logo2.png" alt="" /></div>
        <h1 className="auth-title">Регистрация</h1>
        <p className="auth-subtitle">Создайте аккаунт для подготовки к ЕНТ</p>

        {errors.general && <div className="alert alert-error">{errors.general}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Логин</label>
            <input className="form-input" name="username" value={form.username}
              onChange={handleChange} placeholder="Введите логин" required />
            {errors.username && <div className="form-error">{errors.username}</div>}
          </div>
          <div className="form-group">
            <label className="form-label">Email</label>
            <input className="form-input" name="email" type="email" value={form.email}
              onChange={handleChange} placeholder="email@example.com" />
          </div>
          <div className="form-group">
            <label className="form-label">Полное имя</label>
            <input className="form-input" name="full_name" value={form.full_name}
              onChange={handleChange} placeholder="Иванов Иван" />
          </div>
          <div className="form-group">
            <label className="form-label">Школа</label>
            <input className="form-input" name="school" value={form.school}
              onChange={handleChange} placeholder="Школа №1" />
          </div>

          <div className="form-group">
            <label className="form-label">Профильные предметы</label>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
              Выберите предметы, по которым будете тренироваться
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {[...mandatorySubjects, ...profileSubjList].map(s => (
                <label key={s.id} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
                  borderRadius: 10, border: profileSubjects.includes(s.id) ? '2px solid var(--primary)' : '1px solid var(--border)',
                  background: profileSubjects.includes(s.id) ? '#eef2ff' : '#fafafa',
                  cursor: 'pointer', transition: 'all 0.1s',
                }}>
                  <input type="checkbox" checked={profileSubjects.includes(s.id)}
                    onChange={() => toggleSubject(s.id)}
                    style={{ width: 18, height: 18, cursor: 'pointer' }} />
                  <span style={{ fontSize: 16 }}>{s.icon}</span>
                  <span style={{ fontWeight: 500, fontSize: 14 }}>{s.name}</span>
                  {s.subject_type === 'mandatory' && (
                    <span style={{ fontSize: 11, color: 'var(--text-secondary)', marginLeft: 'auto' }}>обязательный</span>
                  )}
                </label>
              ))}
            </div>
            {errors.profile_subjects && <div className="form-error">{errors.profile_subjects}</div>}
          </div>

          <div className="form-group">
            <label className="form-label">Пароль</label>
            <input className="form-input" name="password" type="password" value={form.password}
              onChange={handleChange} placeholder="Минимум 8 символов" required />
            {errors.password && <div className="form-error">{errors.password}</div>}
          </div>
          <div className="form-group">
            <label className="form-label">Подтвердите пароль</label>
            <input className="form-input" name="password_confirm" type="password"
              value={form.password_confirm} onChange={handleChange} required />
            {errors.password_confirm && <div className="form-error">{errors.password_confirm}</div>}
          </div>
          <button className="btn btn-primary btn-lg" style={{ width: '100%' }} disabled={loading}>
            {loading ? <span className="spinner"></span> : 'Создать аккаунт'}
          </button>
        </form>

        <div className="auth-link">
          Уже есть аккаунт? <Link to="/login">Войти</Link>
        </div>
      </div>
    </div>
  )
}