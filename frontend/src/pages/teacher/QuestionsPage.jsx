import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { questionsAPI, subjectsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import { Plus, X, Edit3, Trash2, BookOpen, HelpCircle, AlertTriangle } from 'lucide-react'

const EMPTY_FORM = {
  text: '',
  topic: '',
  difficulty: 'medium',
  explanation: '',
  image: '',
  answers: [
    { text: '', is_correct: true },
    { text: '', is_correct: false },
    { text: '', is_correct: false },
    { text: '', is_correct: false },
  ],
}

const DIFF_LABELS = { easy: 'Лёгкий', medium: 'Средний', hard: 'Сложный' }

export default function QuestionsPage() {
  const [searchParams] = useSearchParams()
  const [questions, setQuestions] = useState([])
  const [subjects, setSubjects] = useState([])
  const [topics, setTopics] = useState([])
  const [filterSubject, setFilterSubject] = useState(searchParams.get('subject') || '')
  const [filterTopic, setFilterTopic] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [errors, setErrors] = useState({})

  useEffect(() => {
    subjectsAPI.list().then(res => setSubjects(res.data))
  }, [])

  useEffect(() => {
    if (filterSubject) {
      subjectsAPI.topics(filterSubject).then(res => setTopics(res.data))
    } else {
      setTopics([])
    }
  }, [filterSubject])

  const loadQuestions = () => {
    setLoading(true)
    const params = {}
    if (filterSubject) params.subject = filterSubject
    if (filterTopic) params.topic = filterTopic
    if (filterSource) params.source_type = filterSource
    questionsAPI.list(params)
      .then(res => setQuestions(res.data))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadQuestions() }, [filterSubject, filterTopic, filterSource])

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
        image: data.image,
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
    if (!form.topic) { setErrors({ topic: 'Выберите тему' }); return }
    try {
      if (editingId) await questionsAPI.update(editingId, form)
      else await questionsAPI.create(form)
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
    try { await questionsAPI.delete(id); loadQuestions() } catch {}
  }

  const setAnswerText = (i, text) => {
    const answers = [...form.answers]
    answers[i] = { ...answers[i], text }
    setForm({ ...form, answers })
  }

  const setAnswerCorrect = (i) => {
    const answers = form.answers.map((a, idx) => ({ ...a, is_correct: idx === i }))
    setForm({ ...form, answers })
  }

  const addAnswer = () => setForm({ ...form, answers: [...form.answers, { text: '', is_correct: false }] })

  const removeAnswer = (i) => {
    if (form.answers.length <= 2) return
    const answers = form.answers.filter((_, idx) => idx !== i)
    if (!answers.some(a => a.is_correct)) answers[0].is_correct = true
    setForm({ ...form, answers })
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Вопросы</h1>
          <p className="page-subtitle">Управление базой вопросов ЕНТ</p>
        </div>
        <button className="btn btn-primary" onClick={openCreate}
          style={{ borderRadius: 12, padding: '10px 18px', display: 'flex', alignItems: 'center', gap: 6 }}>
          <Plus size={16} /> Добавить вопрос
        </button>
      </div>

      <div className="card" style={{ padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <select value={filterSubject} onChange={e => { setFilterSubject(e.target.value); setFilterTopic('') }}
            style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff', cursor: 'pointer', maxWidth: 220 }}>
            <option value="">Все предметы</option>
            {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
          </select>
          <select value={filterTopic} onChange={e => setFilterTopic(e.target.value)} disabled={!filterSubject}
            style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff', cursor: 'pointer', maxWidth: 220 }}>
            <option value="">Все темы</option>
            {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <select value={filterSource} onChange={e => setFilterSource(e.target.value)}
            style={{ height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 13, background: '#fff', cursor: 'pointer', maxWidth: 180 }}>
            <option value="">Все базы</option>
            <option value="collected">Собранные (ЕНТ)</option>
            <option value="authorial">Авторские</option>
          </select>
        </div>
      </div>

      {showForm && (
        <div className="card" style={{ padding: 24, marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <h3 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>
              {editingId ? 'Редактировать вопрос' : 'Новый вопрос'}
            </h3>
            <button onClick={() => setShowForm(false)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: 'var(--text-secondary)' }}>
              <X size={18} strokeWidth={1.5} />
            </button>
          </div>
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: 4 }}>Текст вопроса *</label>
              <textarea rows={3} value={form.text} onChange={e => setForm({ ...form, text: e.target.value })}
                placeholder="Введите текст вопроса..."
                style={{ width: '100%', borderRadius: 10, border: '1px solid var(--border)', padding: '10px 14px', fontSize: 14, background: '#fff', resize: 'vertical' }} />
              {errors.text && <div style={{ color: '#dc2626', fontSize: 12, marginTop: 4 }}>{errors.text}</div>}
            </div>

            <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: 4 }}>Тема *</label>
                <select value={form.topic} onChange={e => setForm({ ...form, topic: e.target.value })}
                  style={{ width: '100%', height: 40, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 14, background: '#fff', cursor: 'pointer' }}>
                  <option value="">Выберите тему</option>
                  {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                {errors.topic && <div style={{ color: '#dc2626', fontSize: 12, marginTop: 4 }}>{errors.topic}</div>}
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: 4 }}>Сложность</label>
                <select value={form.difficulty} onChange={e => setForm({ ...form, difficulty: e.target.value })}
                  style={{ width: '100%', height: 40, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px', fontSize: 14, background: '#fff', cursor: 'pointer' }}>
                  <option value="easy">Лёгкий</option>
                  <option value="medium">Средний</option>
                  <option value="hard">Сложный</option>
                </select>
              </div>
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: 4 }}>Объяснение (необязательно)</label>
              <textarea rows={2} value={form.explanation} onChange={e => setForm({ ...form, explanation: e.target.value })}
                placeholder="Объяснение правильного ответа..."
                style={{ width: '100%', borderRadius: 10, border: '1px solid var(--border)', padding: '10px 14px', fontSize: 14, background: '#fff', resize: 'vertical' }} />
            </div>

            {form.image && (
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: 4 }}>Текущее изображение</label>
                <img src={form.image} alt="" style={{ maxWidth: '100%', maxHeight: 300, borderRadius: 10 }} />
              </div>
            )}

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: 8 }}>
                Варианты ответов * <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>(отметьте правильный)</span>
              </label>
              {form.answers.map((ans, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
                  <input type="radio" name="correct-answer" checked={ans.is_correct}
                    onChange={() => setAnswerCorrect(i)}
                    style={{ width: 18, height: 18, accentColor: 'var(--primary)', cursor: 'pointer', flexShrink: 0 }} />
                  <input value={ans.text} onChange={e => setAnswerText(i, e.target.value)}
                    placeholder={`Вариант ${i + 1}`}
                    style={{
                      flex: 1, height: 40, borderRadius: 8, border: '1px solid var(--border)',
                      padding: '0 12px', fontSize: 14, background: ans.is_correct ? 'rgba(16,185,129,0.04)' : '#fff',
                    }} />
                  {form.answers.length > 2 && (
                    <button type="button" onClick={() => removeAnswer(i)}
                      style={{
                        width: 32, height: 32, borderRadius: 8, border: 'none',
                        background: 'rgba(239,68,68,0.06)', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>
                      <X size={14} color="#dc2626" />
                    </button>
                  )}
                </div>
              ))}
              {errors.answers && <div style={{ color: '#dc2626', fontSize: 12, marginTop: 4 }}>{errors.answers}</div>}
              <button type="button" onClick={addAnswer}
                style={{
                  marginTop: 8, padding: '8px 16px', borderRadius: 8, border: '1px dashed var(--border)',
                  background: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)',
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                }}>
                + Добавить вариант
              </button>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" className="btn btn-primary"
                style={{ borderRadius: 12, padding: '10px 22px', fontWeight: 600 }}>
                {editingId ? 'Сохранить' : 'Создать вопрос'}
              </button>
              <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}
                style={{ borderRadius: 12, padding: '10px 22px' }}>
                Отмена
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>
          Всего вопросов: {questions.length}
        </div>
        {loading ? (
          <div className="text-center py-4"><div className="spinner"></div></div>
        ) : questions.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>
            <HelpCircle size={40} strokeWidth={1.5} style={{ opacity: 0.3, marginBottom: 12 }} />
            <p>Вопросов не найдено. Создайте первый!</p>
          </div>
        ) : (
          <div>
            {questions.map(q => (
              <div key={q.id} style={{
                padding: '18px 20px', borderBottom: '1px solid var(--border)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 14 }}><FormattedText text={q.text} /></div>
                    {q.image && (
                      <div style={{ textAlign: 'center', margin: '8px 0' }}>
                        <img src={q.image} alt="" style={{ maxWidth: '100%', maxHeight: 200, borderRadius: 8 }} />
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 100, fontSize: 11, fontWeight: 600,
                        background: 'rgba(99,102,241,0.08)', color: 'var(--primary)',
                      }}>{q.subject_name}</span>
                      <span style={{
                        padding: '2px 8px', borderRadius: 100, fontSize: 11, fontWeight: 600,
                        background: 'rgba(16,185,129,0.08)', color: '#065F46',
                      }}>{q.topic_name}</span>
                      <span style={{
                        padding: '2px 8px', borderRadius: 100, fontSize: 11, fontWeight: 600,
                        background: q.difficulty === 'easy' ? 'rgba(16,185,129,0.1)' : q.difficulty === 'hard' ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)',
                        color: q.difficulty === 'easy' ? '#065F46' : q.difficulty === 'hard' ? '#991B1B' : '#92400E',
                      }}>{DIFF_LABELS[q.difficulty]}</span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <button onClick={() => openEdit(q)}
                      style={{
                        padding: '6px 12px', borderRadius: 8, border: '1px solid var(--border)',
                        background: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600,
                        display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text)',
                      }}>
                      <Edit3 size={13} strokeWidth={1.5} /> Изменить
                    </button>
                    <button onClick={() => handleDelete(q.id)}
                      style={{
                        width: 34, height: 34, borderRadius: 8, border: '1px solid rgba(239,68,68,0.2)',
                        background: 'rgba(239,68,68,0.04)', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                      <Trash2 size={14} color="#dc2626" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
