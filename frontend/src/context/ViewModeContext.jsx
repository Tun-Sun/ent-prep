import { createContext, useContext, useState } from 'react'
import { useAuth } from './AuthContext'

// Переключатель «Кабинет учителя ↔ Кабинет ученика» (Блок 1).
//
// Владелец платформы проверяет оба интерфейса своими глазами и не хочет каждый раз
// перелогиниваться: режим решает только то, какие пункты видны в сайдбаре и какой
// экран лежит на `/`. Права по-прежнему решает сервер по роли — переключатель не
// даёт ученику тренерских экранов. Выбор живёт в `localStorage`, поэтому после
// перезагрузки человек остаётся там, где был.

const KEY = 'ent.ui_mode'

/** Кому показывать переключатель: сотрудникам и тем, у кого есть тренерская роль. */
export function canSwitchMode(user) {
  return !!user && (user.is_staff === true || user.role === 'teacher' || user.role === 'admin')
}

function resolve(user, saved) {
  if (!canSwitchMode(user)) return 'student'
  return saved === 'student' ? 'student' : 'teacher'
}

const ViewModeContext = createContext({ mode: 'student', setMode: () => {}, switchable: false })

export function ViewModeProvider({ children }) {
  const { user } = useAuth()
  const [saved, setSaved] = useState(() => localStorage.getItem(KEY))
  const mode = resolve(user, saved)

  const setMode = (next) => {
    localStorage.setItem(KEY, next)
    setSaved(next)
  }

  return (
    <ViewModeContext.Provider value={{ mode, setMode, switchable: canSwitchMode(user) }}>
      {children}
    </ViewModeContext.Provider>
  )
}

export const useViewMode = () => useContext(ViewModeContext)
