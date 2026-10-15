// Дежурный вход в урок «как ученик» (Шаг 6.6).
//
// Ссылку из шаблона GetCourse проверяют во вкладке браузера, и тренеру нужно одним
// кликом увидеть экран сдачи. Ключи сессии лежат в `localStorage` и общие для всего
// адреса, поэтому вход тестовым учеником обязан сохранить прежнюю сессию: без этого
// тренер остался бы в уроке чужим человеком и потерял бы свой вход.

const RETURN_KEY = 'lesson_preview_return'

export function enterLessonAsDemoStudent({ assignmentId, token, back = '/teacher/assign' }) {
  const access = localStorage.getItem('access_token')
  if (access) {
    localStorage.setItem(RETURN_KEY, JSON.stringify({
      access,
      refresh: localStorage.getItem('refresh_token') || '',
      back,
    }))
  }
  // Полный переход, а не запрос через `axios`: сервер отвечает 302 на `/sso#access=…`,
  // и только браузер донесёт ключ до экрана, который переложит его в хранилище.
  const q = new URLSearchParams({ assignment_id: String(assignmentId), lesson_token: token, demo: '1' })
  window.location.assign('/api/lesson/join/?' + q.toString())
}

export function savedReturnSession() {
  const raw = localStorage.getItem(RETURN_KEY)
  if (!raw) return null
  try {
    const saved = JSON.parse(raw)
    return saved && saved.access ? saved : null
  } catch {
    localStorage.removeItem(RETURN_KEY)
    return null
  }
}

/** Вернуть тренерскую сессию и отдать адрес, откуда он ушёл в тестовый вход. */
export function leaveDemoSession() {
  const saved = savedReturnSession()
  if (!saved) return null
  localStorage.removeItem(RETURN_KEY)
  localStorage.setItem('access_token', saved.access)
  if (saved.refresh) localStorage.setItem('refresh_token', saved.refresh)
  else localStorage.removeItem('refresh_token')
  return saved.back || '/teacher/assign'
}
