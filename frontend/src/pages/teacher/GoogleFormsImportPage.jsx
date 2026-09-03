import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { importAPI, subjectsAPI } from '../../api'

export default function GoogleFormsImportPage() {
  const [subjects, setSubjects] = useState([])
  const [formId, setFormId] = useState('')
  const [subjectSlug, setSubjectSlug] = useState('')
  const [topicName, setTopicName] = useState('')
  const [language, setLanguage] = useState('ru')
  const [year, setYear] = useState(new Date().getFullYear())

  const [step, setStep] = useState('form') // form | preview | result
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    subjectsAPI.list().then(res => {
      setSubjects(res.data)
      if (res.data.length > 0) setSubjectSlug(res.data[0].slug)
    })
  }, [])

  const handlePreview = async (e) => {
    e.preventDefault()
    if (!formId.trim() || !topicName.trim()) {
      setError('Заполните ID формы и тему')
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await importAPI.previewFromUrl({
        form_id: formId,
        subject_slug: subjectSlug,
        topic_name: topicName,
        language, year: Number(year) || null,
      })
      setPreview(res.data)
      setStep('preview')
    } catch (err) {
      setError(err.response?.data?.error || 'Не удалось подтянуть форму')
    } finally {
      setLoading(false)
    }
  }

  const handleImport = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await importAPI.importFromUrl({
        form_id: formId,
        subject_slug: subjectSlug,
        topic_name: topicName,
        language, year: Number(year) || null,
      })
      setResult(res.data)
      setStep('result')
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка импорта')
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setStep('form')
    setPreview(null)
    setResult(null)
    setError('')
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">📋 Импорт из Google Forms</h1>
        <p className="page-subtitle">Подтяните вопросы по ссылке автоматически</p>
      </div>

      {/* Навигация */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        <span className={`badge ${step === 'form' ? 'badge-primary' : ''}`} style={{ padding: '6px 14px', borderRadius: 6, fontSize: 14 }}>
          1. Ссылка и параметры
        </span>
        <span className={`badge ${step === 'preview' ? 'badge-primary' : ''}`} style={{ padding: '6px 14px', borderRadius: 6, fontSize: 14, opacity: step === 'form' ? 0.4 : 1 }}>
          2. Предпросмотр
        </span>
        <span className={`badge ${step === 'result' ? 'badge-primary' : ''}`} style={{ padding: '6px 14px', borderRadius: 6, fontSize: 14, opacity: step !== 'result' ? 0.4 : 1 }}>
          3. Результат
        </span>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {/* Шаг 1: Форма */}
      {step === 'form' && (
        <div className="card">
          <div className="card-header">Ссылка на Google Form</div>
          <form onSubmit={handlePreview}>
            <div className="form-group">
              <label className="form-label">Ссылка или ID формы *</label>
              <input
                type="text"
                className="form-input"
                placeholder="https://docs.google.com/forms/d/e/.../viewform"
                value={formId}
                onChange={e => setFormId(e.target.value)}
                required
                style={{ width: '100%', maxWidth: 600 }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 12 }}>
              <div className="form-group">
                <label className="form-label">Предмет *</label>
                <select className="form-select" value={subjectSlug} onChange={e => setSubjectSlug(e.target.value)}>
                  {subjects.map(s => (
                    <option key={s.slug} value={s.slug}>{s.icon} {s.name}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Тема *</label>
                <input className="form-input" placeholder="Название темы" value={topicName}
                  onChange={e => setTopicName(e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label">Язык</label>
                <select className="form-select" value={language} onChange={e => setLanguage(e.target.value)}>
                  <option value="ru">Русский</option>
                  <option value="kk">Казахский</option>
                  <option value="en">English</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Год</label>
                <input className="form-input" type="number" value={year}
                  onChange={e => setYear(e.target.value)} />
              </div>
            </div>
            <div style={{ marginTop: 20 }}>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? <><span className="spinner"></span> Подтягиваем...</> : '🔍 Подтянуть и показать предпросмотр'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Шаг 2: Предпросмотр */}
      {step === 'preview' && preview?.meta && (
        <div className="card">
          <div className="card-header">Предпросмотр</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
            {[
              { label: 'Найдено вопросов', val: preview.meta.questions_in_form, color: '#EFF6FF' },
              { label: 'С правильными ответами', val: preview.meta.with_correct_answers, color: preview.meta.with_correct_answers > 0 ? '#D1FAE5' : '#FEF3C7' },
              { label: 'С картинками', val: preview.meta.with_images, color: '#F3E8FF' },
              { label: 'Источник', val: preview.meta.used_api ? 'API' : 'Скрапинг', color: '#F0F9FF' },
            ].map((s, i) => (
              <div key={i} style={{ padding: 16, borderRadius: 10, background: s.color, textAlign: 'center' }}>
                <div style={{ fontSize: 28, fontWeight: 800 }}>{s.val}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{s.label}</div>
              </div>
            ))}
          </div>
          {preview.meta.form_title && (
            <p style={{ marginBottom: 8 }}><strong>Форма:</strong> {preview.meta.form_title}</p>
          )}
          {preview.meta.used_scrape && !preview.meta.used_api && (
            <div className="alert" style={{ background: '#FEF3C7', marginBottom: 16, padding: 12, borderRadius: 8 }}>
              ⚠ Правильные ответы не получены — вопросы будут импортированы как <em>черновики</em>. Причина и что делать — в предупреждениях ниже.
            </div>
          )}
          {preview.meta.warnings?.length > 0 && (
            <div style={{ marginBottom: 16, fontSize: 13, color: '#92400E' }}>
              {preview.meta.warnings.map((w, i) => <div key={i}>• {w}</div>)}
            </div>
          )}
          <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
            <button className="btn btn-primary" onClick={handleImport} disabled={loading}>
              {loading ? <><span className="spinner"></span> Импортируем...</> : '✅ Подтвердить импорт'}
            </button>
            <button className="btn" onClick={reset} disabled={loading}>← Назад</button>
          </div>
        </div>
      )}

      {/* Шаг 3: Результат */}
      {step === 'result' && result?.result && (
        <div className="card">
          <div className="card-header">Результат импорта</div>
          <div className="alert alert-success" style={{ fontSize: 16, fontWeight: 600, padding: 16, borderRadius: 10 }}>
            ✅ Импорт завершён
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12, marginTop: 12, marginBottom: 16 }}>
            {[
              { label: 'Создано', val: result.result.created, color: '#D1FAE5' },
              { label: 'Дубликаты', val: result.result.skipped_duplicates, color: '#F3F4F6' },
              { label: 'Без ответа', val: result.result.drafted_no_correct, color: result.result.drafted_no_correct > 0 ? '#FEE2E2' : '#F3F4F6' },
              { label: 'Картинки', val: result.attached_images || 0, color: '#F3E8FF' },
            ].map((s, i) => (
              <div key={i} style={{ padding: 16, borderRadius: 10, background: s.color, textAlign: 'center' }}>
                <div style={{ fontSize: 28, fontWeight: 800 }}>{s.val}</div>
                <div style={{ fontSize: 12 }}>{s.label}</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <Link to="/teacher/questions" className="btn btn-primary">Перейти к вопросам →</Link>
            <button className="btn" onClick={reset}>Импортировать ещё</button>
            <Link to="/teacher/import" className="btn">← Импорт Excel</Link>
          </div>
        </div>
      )}

      {/* Подсказка */}
      <div className="card" style={{ marginTop: 20, background: '#FFF7ED' }}>
        <div className="card-header">💡 Как работает</div>
        <ol style={{ fontSize: 14, lineHeight: 1.8, padding: '0 0 0 20px', color: 'var(--text-secondary)' }}>
          <li>Откройте Google Form → нажмите <strong>«Расшарить»</strong> → выберите <strong>«Неограниченный доступ»</strong></li>
          <li>Скопируйте ссылку и вставьте сюда</li>
          <li>Выберите предмет и укажите тему</li>
          <li>Нажмите «Подтянуть» — сервер скачает вопросы, варианты и картинки</li>
          <li>Проверьте предпросмотр и подтвердите импорт</li>
        </ol>
        <p style={{ fontSize: 13, marginTop: 8 }}>
          <strong>Правильные ответы:</strong> для получения правильных ответов нужно расшарить форму на сервисный аккаунт Google (обратитесь к администратору).
          Без этого вопросы импортируются как черновики — ответы нужно будет отметить вручную.
        </p>
      </div>
    </div>
  )
}
