import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { subjectsAPI, groupsAPI } from '../../api'
import { GRADUATION_TRACKS } from '../../constants/tracks'

// Экран регистрации (Блок 2.2): до этого платформа была тренажёром ЕНТ для
// одиннадцатиклассников, теперь в неё входят ученики 5–11 классов и преподаватели —
// поэтому две вкладки, обязательный класс и код преподавателя.
//
// Роль решает сервер: вкладка «преподаватель» без верного кода из `TEACHER_INVITE_CODE`
// даёт 400, а не тренерский вход. Ответ сервера (`role`) решает и адрес после входа.
const GRADES = [5, 6, 7, 8, 9, 10, 11]
// Физика и математика — то, ради чего в центр приходят чаще всего: их видим
// первыми и держим предвыбранными. Совпадает с `DEFAULT_STUDENT_SLUGS` на сервере.
const PRIORITY_SLUGS = ['physics', 'math', 'math_profile']
const DEFAULT_SUBJECT_SLUGS = ['physics', 'math']

export default function RegisterPage() {
  const [kind, setKind] = useState('student')
  const [form, setForm] = useState({
    username: '', email: '', password: '', full_name: '', school: '',
    grade: null, track: '', subject: '', invite_code: '', group_id: null,
  })
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [subjects, setSubjects] = useState([])
  const [groups, setGroups] = useState([])
  const [profileSubjects, setProfileSubjects] = useState([])
  const { register } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    subjectsAPI.forRegistration().then(res => {
      const list = Array.isArray(res.data) ? res.data : []
      const sorted = list.slice().sort((a, b) => {
        const pa = PRIORITY_SLUGS.indexOf(a.slug)
        const pb = PRIORITY_SLUGS.indexOf(b.slug)
        if (pa !== pb) return pa === -1 ? 1 : -1
        return 0
      })
      setSubjects(sorted)
      // Профильные предметы по умолчанию — те же два, что ставит сервер: ребёнок
      // видит предвыбранные чипы, а не пустой список.
      setProfileSubjects(sorted.filter(s => DEFAULT_SUBJECT_SLUGS.includes(s.slug)).map(s => s.id))
    }).catch(() => {})
    // Группы нужны только 11-классникам, но список публичный и маленький.
    groupsAPI.publicList().then(res => {
      setGroups(Array.isArray(res.data) ? res.data : [])
    }).catch(() => {})
  }, [])

  const set = (name, value) => setForm(prev => ({ ...prev, [name]: value }))

  // 5–10 — только школа, 11 — развилка ЕНТ/NUET. При смене класса старый трек
  // не тащим: иначе школьник унёс бы в payload ЕНТ-трек, а сервер молча сбросил.
  const chooseGrade = (grade) => {
    setForm(prev => ({
      ...prev,
      grade,
      track: grade === 11 ? (prev.track === 'ent' || prev.track === 'nuet' ? prev.track : '') : 'school',
    }))
  }

  const visibleSubjects = subjects.filter(
    s => !s.track || !form.track || s.track === form.track
  )
  const showProfileSubjects = kind === 'student' && form.grade === 11 && form.track === 'ent'

  const toggleSubject = (id) => {
    setProfileSubjects(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrors({})
    if (kind === 'student' && !form.grade) {
      setErrors({ grade: 'Выберите класс' })
      return
    }
    if (kind === 'student' && form.grade === 11 && !['ent', 'nuet'].includes(form.track)) {
      setErrors({ track: 'Выберите ЕНТ или NUET' })
      return
    }
    setLoading(true)
    const payload = kind === 'student'
      ? {
          account_type: 'student', username: form.username, password: form.password,
          full_name: form.full_name, school: form.school, grade: form.grade,
          track: form.track || undefined,
          email: form.email,
          group_id: form.grade === 11 ? form.group_id : null,
          // Профильные предметы — только у ЕНТ: у школы и NUET своего каталога
          // пока нет, и список ЕНТ-предметов им не принадлежит.
          profile_subjects: showProfileSubjects ? profileSubjects : [],
        }
      : {
          account_type: 'teacher', username: form.username, password: form.password,
          full_name: form.full_name, email: form.email, subject: form.subject || null,
          invite_code: form.invite_code,
        }
    try {
      const me = await register(payload)
      navigate(me.role === 'student' ? '/' : '/teacher', { replace: true })
    } catch (err) {
      const data = err.response?.data
      if (data) {
        const errs = {}
        Object.keys(data).forEach(k => { errs[k] = Array.isArray(data[k]) ? data[k][0] : data[k] })
        setErrors(errs)
      } else {
        setErrors({ general: 'Ошибка регистрации' })
      }
    } finally {
      setLoading(false)
    }
  }

  const nameField = (
    <div className="form-group">
      <label className="form-label">Фамилия и Имя</label>
      <input className="form-input" value={form.full_name}
        onChange={e => set('full_name', e.target.value)} placeholder="Ахметов Арман" required />
      {errors.full_name && <div className="form-error">{errors.full_name}</div>}
    </div>
  )

  const passwordField = (
    <div className="form-group">
      <label className="form-label">Пароль</label>
      <div className="password-wrap">
        <input className="form-input" type={showPassword ? 'text' : 'password'}
          value={form.password} onChange={e => set('password', e.target.value)}
          placeholder="Минимум 8 символов" required autoComplete="new-password" />
        <button type="button" className="password-eye"
                onClick={() => setShowPassword(v => !v)}
                aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}>
          {showPassword ? '🙈' : '👁'}
        </button>
      </div>
      {errors.password && <div className="form-error">{errors.password}</div>}
    </div>
  )

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo"><img src="/assets/logo2.png" alt="" /></div>
        <h1 className="auth-title">Регистрация в INTELLECT</h1>
        <p className="auth-subtitle">Единая учебная платформа 5–11 классов</p>

        {errors.general && <div className="alert alert-error">{errors.general}</div>}

        <div className="reg-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={kind === 'student'}
                  className={'reg-tab' + (kind === 'student' ? ' active' : '')}
                  onClick={() => { setKind('student'); setErrors({}) }}>
            🎒 Ученик
          </button>
          <button type="button" role="tab" aria-selected={kind === 'teacher'}
                  className={'reg-tab' + (kind === 'teacher' ? ' active' : '')}
                  onClick={() => { setKind('teacher'); setErrors({}) }}>
            👨‍🏫 Преподаватель
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {nameField}

          {kind === 'student' && (
            <div className="form-group">
              <label className="form-label">Класс</label>
              <div className="grade-chips">
                {GRADES.map(g => (
                  <button type="button" key={g}
                          className={'grade-chip' + (form.grade === g ? ' active' : '')}
                          onClick={() => chooseGrade(g)}>{g}</button>
                ))}
              </div>
              {errors.grade && <div className="form-error">{errors.grade}</div>}
            </div>
          )}

          {kind === 'student' && form.grade === 11 && (
            <div className="form-group">
              <label className="form-label">Трек подготовки</label>
              <div className="grade-chips">
                {GRADUATION_TRACKS.map(option => (
                  <button type="button" key={option.value}
                          className={'grade-chip' + (form.track === option.value ? ' active' : '')}
                          onClick={() => set('track', option.value)}>
                    {option.label}
                  </button>
                ))}
              </div>
              <p className="form-hint">ЕНТ или NUET — от этого зависит каталог предметов.</p>
              {errors.track && <div className="form-error">{errors.track}</div>}
            </div>
          )}

          {kind === 'student' && form.grade === 11 && groups.length > 0 && (
            <div className="form-group">
              <label className="form-label">Группа (не обязательно)</label>
              <div className="grade-chips" style={{ flexWrap: 'wrap' }}>
                <button type="button"
                  className={'grade-chip' + (!form.group_id ? ' active' : '')}
                  onClick={() => set('group_id', null)}>
                  Без группы
                </button>
                {groups.map(group => (
                  <button type="button" key={group.id}
                    className={'grade-chip' + (form.group_id === group.id ? ' active' : '')}
                    onClick={() => set('group_id', group.id)}>
                    {group.name}
                  </button>
                ))}
              </div>
              <p className="form-hint">Позже группу можно поменять у преподавателя.</p>
              {errors.group_id && <div className="form-error">{errors.group_id}</div>}
            </div>
          )}

          {kind === 'teacher' && (
            <div className="form-group">
              <label className="form-label">Предмет преподавания (не обязательно)</label>
              <select className="form-input" value={form.subject}
                      onChange={e => set('subject', e.target.value)}>
                <option value="">Ещё не выбрал</option>
                {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Логин</label>
            <input className="form-input" value={form.username}
              onChange={e => set('username', e.target.value)} placeholder="armankh" required />
            {errors.username && <div className="form-error">{errors.username}</div>}
          </div>

          {kind === 'teacher' && (
            <div className="form-group">
              <label className="form-label">Email</label>
              <input className="form-input" type="email" value={form.email}
                onChange={e => set('email', e.target.value)} placeholder="email@example.com" required />
              {errors.email && <div className="form-error">{errors.email}</div>}
            </div>
          )}

          {passwordField}

          {kind === 'teacher' && (
            <div className="form-group">
              <label className="form-label">Инвайт-код центра</label>
              <input className="form-input" value={form.invite_code}
                onChange={e => set('invite_code', e.target.value)}
                placeholder="его выдаёт администратор" required autoComplete="off" />
              <p className="form-hint">
                Тренерский вход открывает банк задач с ответами и разборами, поэтому
                он только по коду.
              </p>
              {errors.invite_code && <div className="form-error">{errors.invite_code}</div>}
            </div>
          )}

          {showProfileSubjects && visibleSubjects.length > 0 && (
            <div className="form-group">
              <label className="form-label">Профильные предметы</label>
              <p className="form-hint">Физику и математику оставим по умолчанию, лишнее можно убрать.</p>
              <div className="subject-chips">
                {visibleSubjects.map(s => (
                  <button type="button" key={s.id}
                          className={'grade-chip' + (profileSubjects.includes(s.id) ? ' active' : '')}
                          onClick={() => toggleSubject(s.id)}>
                    {s.icon} {s.name}
                  </button>
                ))}
              </div>
              {errors.profile_subjects && <div className="form-error">{errors.profile_subjects}</div>}
            </div>
          )}

          {kind === 'student' && (
            <div className="form-group">
              <label className="form-label">Школа (не обязательно)</label>
              <input className="form-input" value={form.school}
                onChange={e => set('school', e.target.value)} placeholder="Школа №1" />
            </div>
          )}

          <button className="btn btn-primary btn-lg" style={{ width: '100%', marginTop: 8 }} disabled={loading}>
            {loading ? <span className="spinner"></span>
                     : (kind === 'student' ? 'Создать аккаунт ученика' : 'Создать аккаунт преподавателя')}
          </button>
        </form>

        <div className="auth-link">
          Уже есть аккаунт? <Link to="/login">Войти</Link>
        </div>
      </div>
    </div>
  )
}
