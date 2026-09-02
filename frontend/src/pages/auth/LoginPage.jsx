import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Неверный логин или пароль')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo"><img src="/assets/logo2.png" alt="" /></div>
        <p className="auth-subtitle">Войдите в свой аккаунт</p>

        {error && <div className="alert alert-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Логин</label>
            <input
              className="form-input"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="Введите логин"
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">Пароль</label>
            <input
              className="form-input"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Введите пароль"
              required
            />
          </div>
          <button className="btn btn-primary btn-lg" style={{ width: '100%' }} disabled={loading}>
            {loading ? <span className="spinner"></span> : 'Войти'}
          </button>
        </form>

        <div className="auth-link">
          Нет аккаунта? <Link to="/register">Зарегистрироваться</Link>
        </div>

        <div style={{ marginTop: 24, padding: '16px 18px', background: '#F0F6FF', borderRadius: 12, fontSize: 13, color: '#4B5563', lineHeight: 1.6 }}>
          <div style={{ fontWeight: 700, color: 'var(--primary)', marginBottom: 6 }}>
            Подготовка к ЕНТ 2026
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <span>📚 34 000+ вопросов по 15 предметам</span>
            <span>🎯 Симуляция ЕНТ в реальном формате — 120 вопросов, 5 предметов</span>
            <span>🤖 AI-разбор ошибок после каждого теста</span>
          </div>
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid rgba(36,59,130,0.12)', fontSize: 12, color: '#6B7280' }}>
            Забыли пароль? Обратитесь к своему преподавателю — он его сбросит.
          </div>
        </div>
      </div>
    </div>
  )
}
