import { useEffect, useRef, useState } from 'react'
import { telegramAPI } from '../../api'

// Кнопка «Log in with Telegram» (вход для учебного чата).
//
// Русскую подпись рисует наш экран, саму кнопку — скрипт Telegram. Подпись ответа
// проверяет только сервер (секрет — SHA256 от токена бота), поэтому сюда попадает
// честный `telegram_id`, а фронт не решает, кто вошёл.
//
// Возврат от Telegram читает страница, а не замыкание внутри виджета. На телефоне
// (особенно в Telegram In-App Browser, откуда ученики открывают ссылки из чата)
// колбэк `data-onauth` теряется при переходе между окнами, и кнопка «ничего не
// делает». Надёжных пути два, и оба приводят к одному запросу на сервер:
//  · `data-auth-url` — виджет сам несёт человека на эту же страницу, дописав в
//    строку запроса `id`, `first_name`, `username`, `auth_date`, `photo_url`, `hash`;
//  · `#tgAuthResult=` — когда мессенджер вернул ответ фрагментом, страница
//    распаковывает его сама, не дожидаясь, пока скрипт Telegram инициализируется.

const WIDGET_SRC = 'https://telegram.org/js/telegram-widget.js?22'

// Поля, которые Telegram подписывает и приносит обратно.
const TG_FIELDS = ['id', 'first_name', 'last_name', 'username', 'photo_url', 'auth_date', 'hash']
const RETURN_MARKER = 'tg_auth'

/** Живёт ли вход через Telegram на сервере: без бота кнопку показывать нельзя. */
export function useTelegramConfig() {
  const [config, setConfig] = useState({ loading: true, enabled: false, botName: '' })
  useEffect(() => {
    telegramAPI.config()
      .then(res => setConfig({
        loading: false,
        enabled: !!res.data.enabled,
        botName: res.data.telegram_bot_username || '',
      }))
      .catch(() => setConfig({ loading: false, enabled: false, botName: '' }))
  }, [])
  return config
}

/**
 * Куда Telegram вернёт ответ: та же страница плюс отметка возврата и урок прямыми
 * параметрами. URL обязан быть абсолютным — относительный виджет разрешил бы против
 * своего домена (oauth.telegram.org), и ученик ушёл бы в чужой путь.
 */
export function telegramReturnUrl(extra) {
  const url = new URL(window.location.href)
  url.hash = ''
  url.searchParams.set(RETURN_MARKER, '1')
  if (extra) {
    if (extra.assignment_id) url.searchParams.set('assignment_id', extra.assignment_id)
    if (extra.lesson_token) url.searchParams.set('lesson_token', extra.lesson_token)
  }
  return url.toString()
}

/** Урок из строки запроса: прямые параметры или вложенная ссылка `next=/sso?...`. */
function lessonFromQuery(q) {
  const id = q.get('assignment_id') || q.get('preview_assignment')
  const token = q.get('lesson_token')
  if (id && token) return { assignment_id: String(id), lesson_token: token }
  const next = q.get('next') || ''
  if (next.startsWith('/sso?')) {
    const inner = new URLSearchParams(next.slice(next.indexOf('?') + 1))
    const nestedId = inner.get('preview_assignment')
    const nestedToken = inner.get('lesson_token')
    if (nestedId && nestedToken) {
      return { assignment_id: String(nestedId), lesson_token: nestedToken }
    }
  }
  return {}
}

function pickFields(get) {
  const data = {}
  TG_FIELDS.forEach(key => {
    const value = get(key)
    if (value) data[key] = String(value)
  })
  return data.id && data.hash ? data : null
}

/** Ответ Telegram в фрагменте адреса: base64(JSON), как его распаковывает сам виджет. */
function readHashReturn() {
  const match = (window.location.hash || '').match(/[#?&]tgAuthResult=([A-Za-z0-9\-_=]*)/)
  if (!match || !match[1]) return null
  let packed = match[1].replace(/-/g, '+').replace(/_/g, '/')
  const pad = packed.length % 4
  if (pad > 1) packed += '===='.slice(0, 5 - pad)
  try {
    // имена учеников кириллицей: atob отдаёт latin-1, без UTF-8 Айдар превратился бы в «Ð'»
    const binary = window.atob(packed)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
    const user = JSON.parse(new TextDecoder('utf-8').decode(bytes))
    return pickFields(key => user[key])
  } catch (e) {
    return null
  }
}

/** Что Telegram уже вернул (в запросе или фрагменте) — или null, если возврата нет. */
export function readTelegramReturn() {
  const query = new URLSearchParams(window.location.search)
  const data = pickFields(key => query.get(key)) || readHashReturn()
  if (!data) return null
  return { data, lesson: lessonFromQuery(query) }
}

/** Ответ бота не должен остаться в адресной строке и в истории браузера. */
function scrubReturnFromAddress() {
  const url = new URL(window.location.href)
  TG_FIELDS.forEach(key => url.searchParams.delete(key))
  url.searchParams.delete(RETURN_MARKER)
  window.history.replaceState(null, '', url.pathname + url.search)
}

/**
 * Приём возврата: страница сама отправляет подписанные поля на `POST /api/auth/telegram/`,
 * кладёт токены в `localStorage` и уходит туда, куда сказал сервер (`/assignments?open=..`).
 * Человек видит ход дела и текст ошибки, а не молчаливый `console.error`.
 *
 * Слушает и `hashchange`: если мессенджер вернулся во фрагмент на тот же адрес,
 * браузер не перезагружает страницу, и одного mount-обработчика не хватило бы —
 * именно так вход и «змирал» на телефоне.
 */
export function useTelegramReturn() {
  const [phase, setPhase] = useState(() => (readTelegramReturn() ? 'waiting' : 'idle'))
  const [error, setError] = useState('')
  const [entered, setEntered] = useState(null)
  const busy = useRef(false)

  useEffect(() => {
    const run = () => {
      if (busy.current) return
      const found = readTelegramReturn()
      if (!found) return
      busy.current = true
      scrubReturnFromAddress()
      setError('')
      setPhase('waiting')

      telegramAPI.login(Object.assign({}, found.data, found.lesson))
        .then(res => {
          localStorage.setItem('access_token', res.data.access)
          localStorage.setItem('refresh_token', res.data.refresh)
          if (res.data.notice) {
            setEntered(res.data)
            setPhase('entered')
          } else {
            window.location.replace(res.data.next)
          }
        })
        .catch(err => {
          // отказ — значит кнопку можно нажать снова, и экран обязан это показать
          busy.current = false
          setPhase('failed')
          setError((err.response && err.response.data && err.response.data.detail) ||
            'Telegram-вход не прошёл. Войдите по логину и паролю.')
        })
    }

    run()
    window.addEventListener('hashchange', run)
    return () => window.removeEventListener('hashchange', run)
  }, [])

  return { waiting: phase === 'waiting', failed: phase === 'failed', error, entered }
}

/** Полоса приёма возврата: пока страница доносит подпись серверу, экран показывает ход. */
export function TelegramReturnPanel({ error }) {
  if (error) return <div className="alert alert-error">{error}</div>
  return (
    <div style={{ padding: '20px 0' }} className="text-center">
      <div className="spinner" style={{ margin: '0 auto' }}></div>
      <p className="text-sm mt-3" style={{ color: 'var(--text-secondary)' }}>
        Выполняем вход через Telegram…
      </p>
    </div>
  )
}

/**
 * `extra` — что приложить к ответу Telegram: `assignment_id` и `lesson_token` из
 * ссылки урока. Они уезжают в `data-auth-url`, чтобы возврат пришёл сразу на урок:
 * в подпись входят только поля Telegram, поэтому лишние параметры её не ломают.
 */
export default function TelegramLoginButton({ botName, extra }) {
  const box = useRef(null)
  // `data-auth-url` виджет читает один раз при инициализации, поэтому строка, а не
  // объект: свежий литерал на каждый рендер пересоздавал бы кнопку.
  const authUrl = telegramReturnUrl(extra)

  useEffect(() => {
    if (!botName || !box.current) return undefined
    const node = box.current
    const script = document.createElement('script')
    script.async = true
    script.src = WIDGET_SRC
    script.setAttribute('data-telegram-login', botName)
    script.setAttribute('data-size', 'large')
    script.setAttribute('data-radius', '10')
    script.setAttribute('data-auth-url', authUrl)
    node.appendChild(script)
    return () => {
      script.remove()
      node.innerHTML = ''
    }
  }, [botName, authUrl])

  return <div ref={box}></div>
}
