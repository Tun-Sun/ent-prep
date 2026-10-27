import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { myAssignmentsAPI } from '../../api'
import { enterLessonAsDemoStudent } from './lessonPreview'
import TelegramLoginButton, {
  TelegramDirectButton, TelegramReturnPanel, useTelegramConfig, useTelegramReturn,
} from './TelegramLoginButton'

// Промежуточная страница входа из урока GetCourse (Шаг 6.1, предпросмотр — Шаг 6.6).
//
// Токен приходит во фрагменте URL (`/sso#access=…`), а не в строке запроса: фрагмент
// не уходит в логи nginx и в `Referer`, поэтому чужая ссылка, попавшая в журнал
// сервера, не становится чужой сессией. Здесь токен перекладывается в
// `localStorage` — ровно туда же, куда его кладёт экран логина, — и страница
// перезагружается уже внутри задания: ученик пароля не видел и не вводил.
//
// Второй случай — `/sso?preview_assignment=..&lesson_token=..`: ссылку шаблона
// открыли во вкладке, и макросы `{uid}`/`{email}` остались нераскрытыми. Сервер
// проверяет подпись урока и редиректит сюда, чтобы человек не видел сырой отказ.
export default function SsoLandingPage() {
  const { user, loading } = useAuth()
  const telegram = useTelegramConfig()
  const [error, setError] = useState('')
  const [preview, setPreview] = useState(null)
  const [notice, setNotice] = useState('')
  // Ответ Telegram приходит на этот же адрес: страница доносит подпись до сервера
  // сама, а не ждёт колбэк виджета, который на телефоне не доживает.
  const tg = useTelegramReturn()
  const attached = useRef(false)

  useEffect(() => {
    if (tg.waiting) return
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
    const query = new URLSearchParams(window.location.search)
    const access = params.get('access')
    const refresh = params.get('refresh')
    // Куда вести: только свой путь. Чужой домен в `next` унёс бы токен ученика
    // на чужую страницу вместе с перезагрузкой.
    const wanted = params.get('next') || '/'
    const next = wanted.startsWith('/') && !wanted.startsWith('//') ? wanted : '/'

    const lesson = Number(query.get('preview_assignment'))
    const token = query.get('lesson_token')
    if (!access && lesson > 0 && token) {
      setPreview({ assignmentId: lesson, token })
      return
    }
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

  // Довести человека из карточки до его же урока: ученик привязывается по подписи и
  // уходит сдавать, тренер-владелец открывается в конструкторе. Адрес отдаёт сервер —
  // экран сам не решает, кому куда идти.
  const ownLesson = () =>
    myAssignmentsAPI.joinPreview(preview.assignmentId, preview.token).then(res => res.data.next)

  // Ученик уже сидит в этом браузере: представляться не надо, подпись урока его
  // привязывает — и он внутри карточки.
  useEffect(() => {
    if (!preview || loading || attached.current) return
    if (!user || user.role !== 'student') return
    attached.current = true
    ownLesson().then(next => window.location.replace(next))
      .catch(() => setNotice('Урок не открылся: подпись не подошла или урок уже отозван.'))
  }, [preview, loading, user])

  // «Остаться в своём аккаунте» — не ссылка на главную: там этого урока в списке нет,
  // и человек решал, что ссылка не работает. Отказ (урок не его) ведёт в свой же
  // список уроков, где он и так сидит.
  const stay = () => {
    ownLesson().then(next => window.location.replace(next))
      .catch(() => window.location.replace(user.role === 'student' ? '/assignments' : '/teacher/assign'))
  }

  // Куда возвращает «Выйти из тестового входа»: обратно на тот экран, с которого
  // человек зашёл в урок, а не на чужой конструктор.
  const back = !user ? '/login' : (user.role === 'student' ? '/assignments' : '/teacher/assign')

  // «Войти по логину и паролю» ведёт не в список уроков, а обратно на эту карточку:
  // после входа подпись урока привяжет ученика к уроку, и он уйдёт сдавать.
  const passwordHref = '/login?next=' +
    encodeURIComponent(window.location.pathname + window.location.search)

  if (tg.waiting) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="card p-6" style={{ maxWidth: 420 }}>
          <TelegramReturnPanel />
        </div>
      </div>
    )
  }

  if (preview) {
    if (loading) {
      return (
        <div className="min-h-screen flex items-center justify-center px-4">
          <div className="card p-6 text-center" style={{ maxWidth: 420 }}>
            <div className="spinner"></div><p className="text-sm mt-3 muted">Проверяем ссылку…</p>
          </div>
        </div>
      )
    }
    if (tg.entered) {
      return (
        <div className="min-h-screen flex items-center justify-center px-4">
          <div className="card p-6" style={{ maxWidth: 460 }}>
            <h2 style={{ fontSize: 16, marginBottom: 10 }}>Вы вошли в платформу</h2>
            {tg.entered.notice && (
              <p className="text-sm" style={{ color: 'var(--danger)' }}>{tg.entered.notice}</p>
            )}
            <div className="mt-4">
              <button className="btn btn-primary" style={{ borderRadius: 10 }}
                      onClick={() => window.location.replace(tg.entered.next)}>
                Открыть мои уроки
              </button>
            </div>
          </div>
        </div>
      )
    }
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="card p-6" style={{ maxWidth: 460 }}>
          <h2 style={{ fontSize: 16, marginBottom: 10 }}>Ссылка открыта вне урока</h2>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Эта ссылка предназначена для вставки внутрь урока GetCourse (там имя и почта
            ученика подставятся автоматически). Войти можно прямо здесь.
          </p>
          {telegram.enabled && !user && (
            <div className="mt-4">
              <TelegramDirectButton
                botId={telegram.botId}
                extra={{ assignment_id: String(preview.assignmentId), lesson_token: preview.token }}
                label="Войти через Telegram и открыть урок" />
              {telegram.botName && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                    или кнопкой Telegram
                  </div>
                  <TelegramLoginButton
                    botName={telegram.botName}
                    retryToken={tg.error} />
                </div>
              )}
            </div>
          )}
          {telegram.loading && <p className="text-sm mt-3 muted">Проверяем вход через Telegram…</p>}
          {(notice || tg.error) && (
            <p className="text-sm mt-3" style={{ color: 'var(--danger)' }}>{notice || tg.error}</p>
          )}
          {user && user.role !== 'student' && (
            <p className="text-sm mt-3" style={{ color: 'var(--text-secondary)' }}>
              Вы вошли как преподаватель: тестовый вход откроется в этой вкладке, а назад
              вернёт кнопка «Выйти из тестового входа» на экране урока.
            </p>
          )}
          <div className="mt-4" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {!user && (
              <button className="btn btn-outline" style={{ borderRadius: 10 }}
                      onClick={() => window.location.assign(passwordHref)}>
                Войти по логину и паролю
              </button>
            )}
            {user && (
              <button className="btn btn-outline" style={{ borderRadius: 10 }} onClick={stay}>
                Остаться в своём аккаунте
              </button>
            )}
          </div>
          <div className="mt-5" style={{ borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <button className="btn btn-outline"
                    style={{ borderRadius: 10, fontSize: 12, padding: '6px 12px' }}
                    onClick={() => enterLessonAsDemoStudent({
                      assignmentId: preview.assignmentId, token: preview.token, back })}>
              Войти в урок как тестовый ученик
            </button>
            <p style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6 }}>
              Демо-режим для преподавателя (общий профиль)
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="card p-6 text-center" style={{ maxWidth: 420 }}>
        {error || tg.error
          ? <p className="text-sm" style={{ color: 'var(--danger)' }}>{error || tg.error}</p>
          : <div><div className="spinner"></div><p className="text-sm mt-3 muted">Открываем урок…</p></div>}
      </div>
    </div>
  )
}
