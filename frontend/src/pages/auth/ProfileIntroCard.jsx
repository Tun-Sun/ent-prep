import { useState } from 'react'
import { authAPI } from '../../api'
import { GRADUATION_TRACKS } from '../../constants/tracks'

// Карточка «Добро пожаловать в INTELLECT!» (Блок 2.3).
//
// Появляется после входа без пароля — по подписи Telegram или из урока GetCourse.
// Мессенджер отдаёт ник и иногда одно имя, а в журнале тренера баллы должны быть
// подписаны настоящим фамилией и классом, иначе его не к чему приложить.
//
// Сохранение идёт через обычный `PATCH /api/auth/profile/`: токен уже лежит в
// `localStorage`, поэтому карточка не изобретает свой эндпоинт.
const GRADES = [5, 6, 7, 8, 9, 10, 11]

export default function ProfileIntroCard({ fullName = '', grade, track = '', next = '/', onSaved }) {
  const [name, setName] = useState(fullName)
  const [chosen, setChosen] = useState(grade || null)
  const [chosenTrack, setChosenTrack] = useState(track || '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const chooseGrade = (value) => {
    setChosen(value)
    // 5–10 — школа; у 11 трек выбирается отдельно и не должен «залипнуть»
    // с прошлого нажатия.
    setChosenTrack(value === 11 ? chosenTrack : '')
  }

  const save = async (event) => {
    event.preventDefault()
    if (!name.trim()) {
      setError('Напишите фамилию и имя')
      return
    }
    if (!chosen) {
      setError('Выберите класс')
      return
    }
    // Сервер не считает профиль заполненным без трека у 11 класса, поэтому
    // карточка сразу спрашивает ЕНТ/NUET, а не оставляет пустое поле.
    if (chosen === 11 && !['ent', 'nuet'].includes(chosenTrack)) {
      setError('Выберите трек: ЕНТ или NUET')
      return
    }
    setSaving(true)
    setError('')
    try {
      await authAPI.updateProfile({
        full_name: name.trim(),
        grade: chosen,
        track: chosen === 11 ? chosenTrack : undefined,
      })
      // Дальше ведёт экран, а не карточка: у Telegram-входа и ссылки урока свои адреса.
      if (onSaved) onSaved()
      else window.location.replace(next)
    } catch (err) {
      setError((err.response && err.response.data && (err.response.data.error || err.response.data.detail)) ||
        'Не сохранилось. Попробуйте ещё раз.')
      setSaving(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title" style={{ fontSize: 20 }}>Добро пожаловать в INTELLECT!</h1>
        <p className="auth-subtitle">Представься, чтобы учитель нашёл твои баллы в журнале</p>

        {error && <div className="alert alert-error">{error}</div>}

        <form onSubmit={save}>
          <div className="form-group">
            <label className="form-label">Фамилия и Имя</label>
            <input className="form-input" value={name} onChange={e => setName(e.target.value)}
              placeholder="Ахметов Арман" />
            <p className="form-hint">Как в школьном журнале, чтобы учитель видел твои результаты</p>
          </div>

          <div className="form-group">
            <label className="form-label">Класс</label>
            <div className="grade-chips">
              {GRADES.map(g => (
                <button type="button" key={g}
                        className={'grade-chip' + (chosen === g ? ' active' : '')}
                        onClick={() => chooseGrade(g)}>{g}</button>
              ))}
            </div>
          </div>

          {chosen === 11 && (
            <div className="form-group">
              <label className="form-label">Трек подготовки</label>
              <div className="grade-chips">
                {GRADUATION_TRACKS.map(option => (
                  <button type="button" key={option.value}
                          className={'grade-chip' + (chosenTrack === option.value ? ' active' : '')}
                          onClick={() => setChosenTrack(option.value)}>
                    {option.label}
                  </button>
                ))}
              </div>
              <p className="form-hint">От трека зависит, какие предметы появятся в кабинете.</p>
            </div>
          )}

          <button className="btn btn-primary btn-lg" style={{ width: '100%', marginTop: 8 }} disabled={saving}>
            {saving ? <span className="spinner"></span> : 'Сохранить и продолжить →'}
          </button>
        </form>
      </div>
    </div>
  )
}
