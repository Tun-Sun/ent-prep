import { useEffect, useState } from 'react'

// Промежуточная страница входа из урока GetCourse (Шаг 6.1).
//
// Токен приходит во фрагменте URL (`/sso#access=…`), а не в строке запроса: фрагмент
// не уходит в логи nginx и в `Referer`, поэтому чужая ссылка, попавшая в журнал
// сервера, не становится чужой сессией. Здесь токен перекладывается в
// `localStorage` — ровно туда же, куда его кладёт экран логина, — и страница
// перезагружается уже внутри задания: ученик пароля не видел и не вводил.
export default function SsoLandingPage() {
  const [error, setError] = useState('')

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
    const access = params.get('access')
    const refresh = params.get('refresh')
    // Куда вести: только свой путь. Чужой домен в `next` унёс бы токен ученика
    // на чужую страницу вместе с перезагрузкой.
    const wanted = params.get('next') || '/'
    const next = wanted.startsWith('/') && !wanted.startsWith('//') ? wanted : '/'
    if (!access) {
      setError('Вход не получился: в ссылке нет ключа. Откройте задание заново из урока или попросите новую ссылку у преподавателя.')
      return
    }
    localStorage.setItem('access_token', access)
    if (refresh) localStorage.setItem('refresh_token', refresh)
    // Полная перезагрузка, а не `navigate`: провайдер авторизации читает токен один
    // раз при старте приложения, и без него ученик ушёл бы на экран логина.
    window.location.replace(next)
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="card p-6 text-center" style={{ maxWidth: 420 }}>
        {error
          ? <p className="text-sm" style={{ color: 'var(--danger)' }}>{error}</p>
          : <div><div className="spinner"></div><p className="text-sm mt-3 muted">Открываем урок…</p></div>}
      </div>
    </div>
  )
}
