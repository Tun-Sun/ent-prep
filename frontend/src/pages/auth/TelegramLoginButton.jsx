import { useEffect, useRef, useState } from 'react'
import { telegramAPI } from '../../api'

// Кнопка «Log in with Telegram» (вход для учебного чата).
//
// Русскую подпись рисует наш экран, саму кнопку — скрипт Telegram: он открывает
// окно мессенджера и возвращает набор полей с подписью `hash`. Подпись проверяет
// только сервер (секрет — SHA256 от токена бота), поэтому сюда попадает честный
// `telegram_id`, а фронт не решает, кто вошёл.

const WIDGET_SRC = 'https://telegram.org/js/telegram-widget.js?22'

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
 * `extra` — что приложить к ответу Telegram: `assignment_id` и `lesson_token` из
 * ссылки урока, чтобы сервер привязал ученика к уроку тем же запросом.
 * `onSuccess(res)` — сюда отдаётся серверный ответ с `access`, `refresh`, `next`.
 */
export default function TelegramLoginButton({ botName, extra, onSuccess, onError, waitHint }) {
  const box = useRef(null)
  const busy = useRef(null)
  const extraRef = useRef(extra)
  const doneRef = useRef(onSuccess)
  const failRef = useRef(onError)
  extraRef.current = extra
  doneRef.current = onSuccess
  failRef.current = onError

  useEffect(() => {
    if (!botName || !box.current) return undefined
    const node = box.current
    // Имя колбэка обязано быть глобальным: скрипт Telegram зовёт его по строке из
    // `data-onauth`. Уникальное — чтобы два виджета на странице не перезаписывали друг друга.
    const callback = 'tgAuthCb' + Math.random().toString(36).slice(2, 8)
    window[callback] = (data) => {
      if (!data) {
        failRef.current && failRef.current('Telegram не прислал данные входа.')
        return
      }
      if (busy.current) busy.current.textContent = 'Заходим в урок…'
      telegramAPI.login(Object.assign({}, data, extraRef.current || {}))
        .then(res => {
          localStorage.setItem('access_token', res.data.access)
          localStorage.setItem('refresh_token', res.data.refresh)
          if (doneRef.current) doneRef.current(res.data)
        })
        .catch(err => {
          if (busy.current) busy.current.textContent = ''
          const detail = err.response && err.response.data && err.response.data.detail
          if (failRef.current) failRef.current(detail || 'Telegram-вход не прошёл. Войдите по логину и паролю.')
        })
    }
    const script = document.createElement('script')
    script.async = true
    script.src = WIDGET_SRC
    script.setAttribute('data-telegram-login', botName)
    script.setAttribute('data-size', 'large')
    script.setAttribute('data-radius', '10')
    script.setAttribute('data-onauth', callback)
    node.appendChild(script)
    return () => {
      delete window[callback]
      script.remove()
      node.innerHTML = ''
    }
  }, [botName])

  return (
    <div>
      <div ref={box}></div>
      <p ref={busy} className="text-sm mt-2" style={{ color: 'var(--text-secondary)', minHeight: 18 }}>
        {waitHint || ''}
      </p>
    </div>
  )
}
