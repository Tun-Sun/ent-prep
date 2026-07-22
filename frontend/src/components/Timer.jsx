import { useState, useEffect, useRef, useCallback } from 'react'

const STORAGE_KEY = 'ent_timer_'

function loadTimer(sessionId, initial) {
  try {
    const saved = localStorage.getItem(STORAGE_KEY + sessionId)
    if (saved) {
      const { expiresAt } = JSON.parse(saved)
      const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000))
      return remaining > 0 ? remaining : 0
    }
  } catch { }
  return initial
}

function saveTimer(sessionId, expiresAt) {
  try {
    localStorage.setItem(STORAGE_KEY + sessionId, JSON.stringify({ expiresAt }))
  } catch { }
}

export default function Timer({ seconds, onTimeout, isActive, sessionId }) {
  const initial = useRef(seconds)
  const [timeLeft, setTimeLeft] = useState(
    () => loadTimer(sessionId, seconds)
  )

  useEffect(() => {
    if (!sessionId) return
    if (timeLeft <= 0) return
    const expiresAt = Date.now() + timeLeft * 1000
    saveTimer(sessionId, expiresAt)
    const interval = setInterval(() => {
      setTimeLeft(prev => {
        const now = Date.now()
        const remaining = Math.max(0, Math.floor((expiresAt - now) / 1000))
        if (remaining <= 0) {
          clearInterval(interval)
          onTimeout?.()
          return 0
        }
        return remaining
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [isActive, sessionId])

  const hours = Math.floor(timeLeft / 3600)
  const minutes = Math.floor((timeLeft % 3600) / 60)
  const secs = timeLeft % 60
  const isDanger = timeLeft < 300
  const isWarning = timeLeft < 600 && !isDanger

  return (
    <div className={`timer ${isDanger ? 'danger' : ''} ${isWarning ? 'warning' : ''}`}>
      {String(hours).padStart(2, '0')}:{String(minutes).padStart(2, '0')}:{String(secs).padStart(2, '0')}
    </div>
  )
}
