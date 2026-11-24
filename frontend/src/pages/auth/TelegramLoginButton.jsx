import { useEffect, useRef, useState } from 'react'
import { telegramAPI } from '../../api'

// Вход через Telegram: крупная кнопка ведёт в том же окне на страницу согласия
// Telegram, а подписанный ответ возвращается на наш адрес фрагментом `#tgAuthResult=`.
//
// Русскую подпись рисует наш экран, подпись ответа проверяет только сервер (секрет —
// SHA256 от токена бота), поэтому сюда попадает честный `telegram_id`, а фронт не
// решает, кто вошёл. Виджет Telegram больше не ставим: на телефоне его попап и iframe
// теряли ответ, а встроенный обработчик портил кириллицу при распаковке base64.

const OAUTH_ORIGIN = 'https://oauth.telegram.org'

// Поля, которые Telegram подписывает и приносит обратно.
const TG_FIELDS = ['id', 'first_name', 'last_name', 'username', 'photo_url', 'auth_date', 'hash']
const RETURN_MARKER = 'tg_auth'

/** Живёт ли вход через Telegram на сервере: без бота кнопку показывать нельзя. */
export function useTelegramConfig() {
  const [config, setConfig] = useState({ loading: true, enabled: false, botName: '', botId: '' })
  useEffect(() => {
    telegramAPI.config()
      .then(res => setConfig({
        loading: false,
        enabled: !!res.data.enabled,
        botName: res.data.telegram_bot_username || '',
        botId: res.data.telegram_bot_id ? String(res.data.telegram_bot_id) : '',
      }))
      .catch(() => setConfig({ loading: false, enabled: false, botName: '', botId: '' }))
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
  // BotFather обычно принимает только голый домен без www. Если ученик зашёл
  // через www, Telegram отвергает вход «domain invalid» — приводим адрес к
  // каноническому и для origin, и для return_to.
  if (url.hostname.startsWith('www.')) url.hostname = url.hostname.slice(4)
  url.searchParams.set(RETURN_MARKER, '1')
  if (extra) {
    if (extra.assignment_id) url.searchParams.set('assignment_id', extra.assignment_id)
    if (extra.lesson_token) url.searchParams.set('lesson_token', extra.lesson_token)
  }
  return url.toString()
}

/**
 * Наш собственный вход без виджета: тот же адрес, на который Telegram ведёт из
 * своего попапа (`telegram-widget.js` строит `oauth.telegram.org/auth?bot_id=…`),
 * только переход делаем в этом же окне. Попапа нет — значит, попап-блокер мобильного
 * Chrome нечему блокировать, а возвращаться Telegram будет на `return_to` фрагментом
 * `#tgAuthResult=`, который страница читает сама.
 *
 * `request_access` не просим: для входа достаточно подписанных полей ученика, а
 * `write` дал бы боту право писать от его имени.
 */
export function telegramAuthUrl(botId, extra) {
  if (!botId) return ''
  const url = new URL(OAUTH_ORIGIN + '/auth')
  url.searchParams.set('bot_id', String(botId))
  const origin = new URL(window.location.origin)
  if (origin.hostname.startsWith('www.')) origin.hostname = origin.hostname.slice(4)
  url.searchParams.set('origin', origin.toString().replace(/\/$/, ''))
  url.searchParams.set('return_to', telegramReturnUrl(extra))
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
  // добивка «====».slice(0, 5 - pad) давала лишний символ: длина после неё не кратна 4,
  // и atob падал, а вход молчал. Нужно ровно 4 - pad знаков '='.
  const pad = packed.length % 4
  if (pad === 2) packed += '=='
  else if (pad === 3) packed += '='
  else if (pad !== 0) return null
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

/**
 * Ответ виджета, присланный в окно сообщением: `{event:'auth_user', auth_data}` от
 * `oauth.telegram.org`. Это единственный путь, при котором адрес страницы не меняется
 * вообще, поэтому без него вход «ничего не делает».
 *
 * Доверие — по origin: сообщение с любого другого домена принесло бы чужой
 * `telegram_id`, а сервер по нему выдал бы сессию.
 */
function readMessageReturn(event) {
  if (!event || event.origin !== OAUTH_ORIGIN) return null
  let body = event.data
  if (typeof body === 'string') {
    try { body = JSON.parse(body) } catch (e) { return null }
  }
  if (!body || body.event !== 'auth_user' || !body.auth_data) return null
  const user = body.auth_data
  return pickFields(key => user[key])
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
 * Слушаем три доставки сразу: уже пришедший ответ (запрос или фрагмент), `hashchange`
 * (мессенджер вернулся во фрагмент на тот же адрес — браузер страницу не перезагружает)
 * и `message` от `oauth.telegram.org` (виджет отдаёт результат сообщением, и адрес при
 * этом остаётся прежним).
 *
 * Старые токены снимаются до запроса: в `localStorage` телефона могла остаться чужая
 * сессия (тестовая ссылка), а вход по Telegram касается только того, чью подпись
 * прислал мессенджер.
 */
export function useTelegramReturn() {
  const [phase, setPhase] = useState(() => (readTelegramReturn() ? 'waiting' : 'idle'))
  const [error, setError] = useState('')
  const [entered, setEntered] = useState(null)
  const [profile, setProfile] = useState(null)
  const busy = useRef(false)

  useEffect(() => {
    const finish = (data, lesson) => {
      if (busy.current) return
      busy.current = true
      scrubReturnFromAddress()
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      setError('')
      setPhase('waiting')

      telegramAPI.login(Object.assign({}, data, lesson))
        .then(res => {
          localStorage.setItem('access_token', res.data.access)
          localStorage.setItem('refresh_token', res.data.refresh)
          // Сервер сам сказал, что ученик ему неизвестен: без фамилии и класса его
          // баллы в журнале тренера висели бы без имени. Карточка — перед уроком.
          if (res.data.need_profile) {
            setProfile(res.data)
            setPhase('profile')
          } else if (res.data.notice) {
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

    const run = () => {
      const found = readTelegramReturn()
      if (found) finish(found.data, found.lesson)
    }
    const onMessage = event => {
      const data = readMessageReturn(event)
      if (data) finish(data, lessonFromQuery(new URLSearchParams(window.location.search)))
    }

    run()
    window.addEventListener('hashchange', run)
    window.addEventListener('message', onMessage)
    return () => {
      window.removeEventListener('hashchange', run)
      window.removeEventListener('message', onMessage)
    }
  }, [])

  return {
    waiting: phase === 'waiting',
    failed: phase === 'failed',
    needsProfile: phase === 'profile',
    error, entered, profile,
  }
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
 * Наша крупная синяя кнопка: переход в этом же окне на страницу согласия Telegram.
 * Работает там, где виджет молчит, — без iframe, без попапа и без чужого скрипта,
 * который решает, как отдать ответ. `botId` приходит с сервера.
 */
export function TelegramDirectButton({ botId, extra, label }) {
  if (!botId) return null
  return (
    <button
      className="btn btn-primary"
      style={{ width: '100%', borderRadius: 10, minHeight: 46, fontSize: 15, fontWeight: 700,
               display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
      onClick={() => { window.location.href = telegramAuthUrl(botId, extra) }}>
      <svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.85-6.11c.73-.33 1.43.18 1.15 1.3l-2.62 12.39c-.19.91-.73 1.13-1.5.71L12.6 16.6l-2.82 2.05z"/>
      </svg>
      {label || 'Войти через Telegram'}
    </button>
  )
}
