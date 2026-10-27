import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import TelegramLoginButton, {
  TelegramDirectButton, TelegramReturnPanel, useTelegramConfig, useTelegramReturn,
} from './TelegramLoginButton'

// Вход в личный кабинет. Ученики учебного чата входят через Telegram: пароль и почта
// им не нужны, а ссылка из чата ведёт сразу на урок. Форма с логином и паролем
// остаётся — ею входят преподаватели и те, у кого Telegram-вход не сработал.
export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [byPassword, setByPassword] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()
  const telegram = useTelegramConfig()
  // Ответ Telegram приходит на этот же адрес (запросом или фрагментом), и страница
  // доносит подпись до сервера сама: на телефоне колбэк виджета не доживает до нас.
  const tg = useTelegramReturn()

  // `next` приходит из ссылки урока (`/login?next=/sso?preview_assignment=…`): после
  // входа человек возвращается туда, где его дождётся подпись урока. Принимается
  // только свой путь — чужой адрес унёс бы сессию с сайта.
  const query = new URLSearchParams(window.location.search)
  const wanted = query.get('next') || '/'
  const next = wanted.startsWith('/') && !wanted.startsWith('//') ? wanted : '/'
  // Урок из вложенной ссылки: Telegram-вход привязывает к нему тем же запросом.
  const lessonHref = next.startsWith('/sso?') ? new URLSearchParams(next.slice(next.indexOf('?') + 1)) : null
  const assignmentId = lessonHref && Number(lessonHref.get('preview_assignment'))
  const lessonToken = lessonHref && lessonHref.get('lesson_token')
  const lesson = assignmentId > 0 && lessonToken
    ? { assignment_id: String(assignmentId), lesson_token: lessonToken } : null

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      navigate(next, { replace: true })
    } catch (err) {
      setError(err.response?.data?.detail || 'Неверный логин или пароль')
    } finally {
      setLoading(false)
    }
  }

  const showTelegram = telegram.enabled && !byPassword

  if (tg.waiting) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <div className="auth-logo"><img src="/assets/logo2.png" alt="" /></div>
          <TelegramReturnPanel />
        </div>
      </div>
    )
  }

  const failure = error || tg.error

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo"><img src="/assets/logo2.png" alt="" /></div>
        <p className="auth-subtitle">
          {showTelegram ? 'Вход для учеников учебного чата' : 'Войдите в свой аккаунт'}
        </p>

        {failure && <div className="alert alert-error">{failure}</div>}

        {telegram.loading && <p className="text-sm muted">Проверяем вход через Telegram…</p>}

        {showTelegram && (
          <div style={{ marginBottom: 18 }}>
            <TelegramDirectButton
              botId={telegram.botId}
              extra={lesson || {}}
              label={lesson ? 'Войти через Telegram и открыть урок' : 'Войти через Telegram'} />
            {telegram.botName && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                  или кнопкой Telegram
                </div>
                <TelegramLoginButton botName={telegram.botName} retryToken={tg.error} />
              </div>
            )}
            {tg.entered && (
              <div style={{ marginTop: 10 }}>
                <p className="text-sm" style={{ color: 'var(--danger)' }}>{tg.entered.notice}</p>
                <button className="btn btn-primary" style={{ width: '100%', marginTop: 8, borderRadius: 10 }}
                        onClick={() => window.location.replace(tg.entered.next)}>
                  Открыть мои уроки
                </button>
              </div>
            )}
            <button className="btn btn-outline" style={{ width: '100%', marginTop: 10, borderRadius: 10 }}
                    onClick={() => setByPassword(true)}>
              Войти по логину и паролю
            </button>
          </div>
        )}

        {(!telegram.enabled || byPassword) && (
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
        )}

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
