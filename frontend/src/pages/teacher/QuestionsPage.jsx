import { useState, useEffect } from 'react'
import { questionsAPI, subjectsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'

const EMPTY_FORM = {
  text: '',
  topic: '',
  difficulty: 'medium',
  explanation: '',
  answers: [
    { text: '', is_correct: true },
    { text: '', is_correct: false },
    { text: '', is_correct: false },
    { text: '', is_correct: false },
  ],
}

const DIFF_LABELS = { easy: 'Лёгкий', medium: 'Средний', hard: 'Сложный' }

export default function QuestionsPage() {
  const [questions, setQuestions] = useState([])
  const [subjects, setSubjects] = useState([])
  const [topics, setTopics] = useState([])
  const [filterSubject, setFilterSubject] = useState('')
  const [filterTopic, setFilterTopic] = useState('')
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [errors, setErrors] = useState({})

  // Загрузка предметов
  useEffect(() => {
    subjectsAPI.list().then(res => setSubjects(res.data))
  }, [])

  // Загрузка тем при смене предмета
  useEffect(() => {
    if (filterSubject) {
      subjectsAPI.topics(filterSubject).then(res => setTopics(res.data))
    } else {
      setTopics([])
    }
  }, [filterSubject])

  // Загрузка вопросов
  const loadQuestions = () => {
    setLoading(true)
    const params = {}
    if (filterSubject) params.subject = filterSubject
    if (filterTopic) params.topic = filterTopic
    questionsAPI.list(params)
      .then(res => setQuestions(res.data))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadQuestions()
  }, [filterSubject, filterTopic])

  const openCreate = () => {
    setForm(EMPTY_FORM)
    setEditingId(null)
    setErrors({})
    setShowForm(true)
  }

  const openEdit = async (q) => {
    try {
      const res = await questionsAPI.retrieve(q.id)
      const data = res.data
      setForm({
        text: data.text,
        topic: data.topic,
        difficulty: data.difficulty,
        explanation: data.explanation,
        answers: data.answers.map(a => ({ text: a.text, is_correct: a.is_correct })),
      })
      setEditingId(q.id)
      setErrors({})
      setShowForm(true)
    } catch {}
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrors({})

    if (!form.topic) {
      setErrors({ topic: 'Выберите тему' })
      return
    }

    try {
      if (editingId) {
        await questionsAPI.update(editingId, form)
      } else {
        await questionsAPI.create(form)
      }
      setShowForm(false)
      loadQuestions()
    } catch (err) {
      const data = err.response?.data
      if (data) {
        const errs = {}
        Object.keys(data).forEach(k => {
          errs[k] = Array.isArray(data[k]) ? data[k][0] : data[k]
        })
        setErrors(errs)
      }
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Удалить этот вопрос?')) return
    try {
      await questionsAPI.delete(id)
      loadQuestions()
    } catch {}
  }

  // Управление ответами в форме
  const setAnswerText = (i, text) => {
    const answers = [...form.answers]
    answers[i] = { ...answers[i], text }
    setForm({ ...form, answers })
  }

  const setAnswerCorrect = (i) => {
    const answers = form.answers.map((a, idx) => ({
      ...a,
      is_correct: idx === i,
    }))
    setForm({ ...form, answers })
  }

  const addAnswer = () => {
    setForm({
      ...form,
      answers: [...form.answers, { text: '', is_correct: false }],
    })
  }

  const removeAnswer = (i) => {
    if (form.answers.length <= 2) return
    const answers = form.answers.filter((_, idx) => idx !== i)
    // Если удалили правильный, делаем первый правильным
    if (!answers.some(a => a.is_correct)) answers[0].is_correct = true
    setForm({ ...form, answers })
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Вопросы</h1>
        <p className="page-subtitle">Управление базой вопросов ЕНТ</p>
      </div>

      {/* Фильтры */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <select
            className="form-select"
            style={{ maxWidth: 250 }}
            value={filterSubject}
            onChange={e => { setFilterSubject(e.target.value); setFilterTopic('') }}
          >
            <option value="">Все предметы</option>
            {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
          </select>
          <select
            className="form-select"
            style={{ maxWidth: 250 }}
            value={filterTopic}
            onChange={e => setFilterTopic(e.target.value)}
            disabled={!filterSubject}
          >
            <option value="">Все темы</option>
            {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <button className="btn btn-primary" onClick={openCreate} style={{ marginLeft: 'auto' }}>
            + Добавить вопрос
          </button>
        </div>
      </div>

      {/* Форма создания/редактирования */}
      {showForm && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-header">
            {editingId ? 'Редактировать вопрос' : 'Новый вопрос'}
          </div>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Текст вопроса *</label>
              <textarea
                className="form-input"
                rows={3}
                value={form.text}
                onChange={e => setForm({ ...form, text: e.target.value })}
                placeholder="Введите текст вопроса..."
                required
              />
              {errors.text && <div className="form-error">{errors.text}</div>}
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label">Тема *</label>
                <select
                  className="form-select"
                  value={form.topic}
                  onChange={e => setForm({ ...form, topic: e.target.value })}
                >
                  <option value="">Выберите тему</option>
                  {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                {errors.topic && <div className="form-error">{errors.topic}</div>}
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label">Сложность</label>
                <select
                  className="form-select"
                  value={form.difficulty}
                  onChange={e => setForm({ ...form, difficulty: e.target.value })}
                >
                  <option value="easy">Лёгкий</option>
                  <option value="medium">Средний</option>
                  <option value="hard">Сложный</option>
                </select>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Объяснение (необязательно)</label>
              <textarea
                className="form-input"
                rows={2}
                value={form.explanation}
                onChange={e => setForm({ ...form, explanation: e.target.value })}
                placeholder="Объяснение правильного ответа..."
              />
            </div>

            <div className="form-group">
              <label className="form-label">
                Варианты ответов * <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>(отметьте правильный)</span>
              </label>
              {form.answers.map((ans, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
                  <input
                    type="radio"
                    name="correct-answer"
                    checked={ans.is_correct}
                    onChange={() => setAnswerCorrect(i)}
                    style={{ width: 20, height: 20 }}
                  />
                  <input
                    className="form-input"
                    value={ans.text}
                    onChange={e => setAnswerText(i, e.target.value)}
                    placeholder={`Вариант ${i + 1}`}
                    required
                  />
                  {form.answers.length > 2 && (
                    <button
                      type="button"
                      className="btn btn-danger"
                      style={{ padding: '8px 12px' }}
                      onClick={() => removeAnswer(i)}
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
              {errors.answers && <div className="form-error">{errors.answers}</div>}
              <button type="button" className="btn btn-outline" onClick={addAnswer} style={{ marginTop: 8 }}>
                + Добавить вариант
              </button>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" className="btn btn-primary">
                {editingId ? 'Сохранить' : 'Создать вопрос'}
              </button>
              <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>
                Отмена
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Список вопросов */}
      <div className="card">
        <div className="card-header">
          Всего вопросов: {questions.length}
        </div>
        {loading ? (
          <div className="text-center"><div className="spinner"></div></div>
        ) : questions.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 32 }}>
            Вопросов не найдено. Создайте первый!
          </p>
        ) : (
          questions.map(q => (
            <div key={q.id} style={{
              padding: '16px 0',
              borderBottom: '1px solid var(--border)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}><FormattedText text={q.text} /></div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <span className="badge badge-medium">{q.subject_name}</span>
                    <span className="badge badge-easy">{q.topic_name}</span>
                    <span className={`badge badge-${q.difficulty}`}>{DIFF_LABELS[q.difficulty]}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-outline" style={{ padding: '6px 12px', fontSize: 13 }} onClick={() => openEdit(q)}>
                    ✏️ Изменить
                  </button>
                  <button className="btn btn-danger" style={{ padding: '6px 12px', fontSize: 13 }} onClick={() => handleDelete(q.id)}>
                    🗑️
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
