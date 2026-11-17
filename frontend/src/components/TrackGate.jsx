import { useState } from 'react'
import { authAPI } from '../api'
import { useAuth } from '../context/AuthContext'
import { GRADUATION_TRACKS, needsTrack } from '../constants/tracks'

// 11-классник из Telegram или GetCourse приходит без трека. Пока он не выбран,
// непонятно, какой каталог показывать и к какому экзамену вести, поэтому модалка
// обязательная и без «крестика». Сервер тем же правилом не даёт стартовать новые
// тесты (`code: track_required`), а старые уроки и результаты не блокирует.
export default function TrackGate() {
  const { user, refreshUser } = useAuth()
  const [saving, setSaving] = useState('')
  const [error, setError] = useState('')

  if (!needsTrack(user)) return null

  const choose = async (track) => {
    setSaving(track)
    setError('')
    try {
      await authAPI.updateProfile({ track })
      await refreshUser()
    } catch (err) {
      const data = err.response?.data
      setError(data?.error || data?.track?.[0] || 'Не сохранилось. Попробуйте ещё раз.')
      setSaving('')
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="track-gate-title">
      <div className="modal" style={{ maxWidth: 440, borderRadius: 'var(--radius)' }}>
        <div className="modal-header">
          <h3 id="track-gate-title" style={{ fontSize: 20, fontWeight: 800 }}>Выберите трек</h3>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 18 }}>
          Вы в 11 классе. От трека зависит, какие предметы и инструменты появятся
          в кабинете: подготовка к ЕНТ или к NUET.
        </p>
        {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {GRADUATION_TRACKS.map(option => (
            <button key={option.value} type="button" className="btn btn-outline"
              disabled={Boolean(saving)}
              onClick={() => choose(option.value)}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                borderRadius: 12, padding: '14px 18px', textAlign: 'left',
              }}>
              <span>
                <span style={{ display: 'block', fontSize: 15, fontWeight: 700 }}>{option.label}</span>
                <span style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)' }}>{option.hint}</span>
              </span>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--primary)' }}>
                {saving === option.value ? 'Сохраняем…' : 'Выбрать'}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
