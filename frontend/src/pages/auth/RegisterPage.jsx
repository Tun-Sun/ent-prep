import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

export default function RegisterPage() {
  const [form, setForm] = useState({
    username: '', email: '', password: '', password_confirm: '',
    full_name: '', school: '', role: 'student',
  })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const { register } = useAuth()
  const navigate = useNavigate()

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrors({})
    setLoading(true)
    try {
      await register(form)
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

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">🎓</div>
        <h1 className="auth-title">Регистрация</h1>
        <p className="auth-subtitle">Создайте аккаунт для подготовки к ЕНТ</p>

        {errors.general && <div className="alert alert-error">{errors.general}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Роль</label>
            <select className="form-select" name="role" value={form.role} onChange={handleChange}>
              <option value="student">Ученик</option>
              <option value="teacher">Учитель</option>
            </select>
          </div>
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
