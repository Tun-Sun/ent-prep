import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { testsAPI, questionsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import { Save, X, ChevronDown, ChevronRight } from 'lucide-react'

export default function AuthorialTestEditorPage() {
  const { formId } = useParams()
  const navigate = useNavigate()
  const [testInfo, setTestInfo] = useState(null)
  const [questions, setQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)
  const [savingId, setSavingId] = useState(null)

  useEffect(() => {
    testsAPI.authorialTestQuestions(formId)
      .then(res => {
        setTestInfo({ subject: res.data.subject, topic: res.data.topic })
        setQuestions(res.data.questions || [])
      })
      .catch(() => alert('Ошибка загрузки'))
      .finally(() => setLoading(false))
  }, [formId])

  const toggleExpand = (id) => {
    setExpandedId(expandedId === id ? null : id)
  }

  const updateQuestion = (qId, field, value) => {
    setQuestions(prev => prev.map(q => q.id === qId ? { ...q, [field]: value } : q))
  }

  const updateAnswer = (qId, aId, field, value) => {
    setQuestions(prev => prev.map(q => {
      if (q.id !== qId) return q
      return {
        ...q,
        answers: q.answers.map(a => a.id === aId ? { ...a, [field]: value } : a),
      }
    }))
  }

  const saveQuestion = async (q) => {
    setSavingId(q.id)
    try {
      await questionsAPI.update(q.id, {
        text: q.text,
        topic: q.topic,
        difficulty: q.difficulty,
        explanation: q.explanation,
        points: q.points,
        answers: q.answers.map(a => ({ id: a.id, text: a.text, is_correct: a.is_correct })),
      })
    } catch {
      alert('Ошибка сохранения вопроса')
    }
    setSavingId(null)
  }

  const deleteQuestion = async (qId) => {
    if (!confirm('Удалить этот вопрос?')) return
    try {
      await questionsAPI.delete(qId)
      setQuestions(prev => prev.filter(q => q.id !== qId))
    } catch {
      alert('Ошибка удаления')
    }
  }

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <button className="btn btn-outline" onClick={() => navigate(-1)}
          style={{ padding: '8px 16px', fontWeight: 700 }}>← Назад</button>
        <div>
          <h1 className="page-title" style={{ margin: 0 }}>Редактор теста</h1>
          {testInfo && <p className="page-subtitle" style={{ margin: 0 }}>{testInfo.subject} — {testInfo.topic} ({questions.length} вопросов)</p>}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {questions.map((q, i) => {
          const isOpen = expandedId === q.id
          return (
            <div key={q.id} style={{ borderRadius: 14, border: '2px solid var(--border)', overflow: 'hidden', background: '#fff' }}>
              <div onClick={() => toggleExpand(q.id)}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 18px', cursor: 'pointer', userSelect: 'none' }}>
                {isOpen ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                <div style={{ flex: 1, minWidth: 0, fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {i + 1}. <FormattedText text={q.text} />
                </div>
                <span className={`badge badge-${q.difficulty === 'easy' ? 'easy' : q.difficulty === 'hard' ? 'hard' : 'medium'}`} style={{ fontSize: 11, flexShrink: 0 }}>
                  {q.difficulty === 'easy' ? 'Лёгкий' : q.difficulty === 'hard' ? 'Сложный' : 'Средний'}
                </span>
              </div>

              {isOpen && (
                <div style={{ padding: '0 18px 18px', borderTop: '1px solid var(--border)' }}>
                  <div style={{ marginTop: 14 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Текст вопроса</label>
                    <textarea className="form-input" rows={3}
                      value={q.text}
                      onChange={e => updateQuestion(q.id, 'text', e.target.value)}
                      style={{ width: '100%', fontSize: 14, padding: 10, borderRadius: 8, border: '1px solid var(--border)', resize: 'vertical' }} />
                  </div>

                  <div style={{ display: 'flex', gap: 16, marginTop: 12 }}>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Сложность</label>
                      <select value={q.difficulty} onChange={e => updateQuestion(q.id, 'difficulty', e.target.value)}
                        className="form-select" style={{ width: 160 }}>
                        <option value="easy">Лёгкий</option>
                        <option value="medium">Средний</option>
                        <option value="hard">Сложный</option>
                      </select>
                    </div>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Баллы</label>
                      <input type="number" min="0" step="0.5" value={q.points ?? 1}
                        onChange={e => updateQuestion(q.id, 'points', parseFloat(e.target.value) || 0)}
                        style={{ width: 80, padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border)', fontSize: 14 }} />
                    </div>
                  </div>

                  <div style={{ marginTop: 12 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Объяснение</label>
                    <textarea className="form-input" rows={2}
                      value={q.explanation || ''}
                      onChange={e => updateQuestion(q.id, 'explanation', e.target.value)}
                      style={{ width: '100%', fontSize: 14, padding: 10, borderRadius: 8, border: '1px solid var(--border)', resize: 'vertical' }}
                      placeholder="Объяснение ответа (необязательно)" />
                  </div>

                  <div style={{ marginTop: 12 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>Варианты ответов</label>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {q.answers.map(a => (
                        <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <input type="radio" name={`correct_${q.id}`} checked={a.is_correct}
                            onChange={() => updateAnswer(q.id, a.id, 'is_correct', true)}
                            style={{ width: 18, height: 18, cursor: 'pointer', flexShrink: 0 }} />
                          <input value={a.text} onChange={e => updateAnswer(q.id, a.id, 'text', e.target.value)}
                            style={{ flex: 1, padding: '8px 10px', borderRadius: 8, border: a.is_correct ? '2px solid var(--success)' : '1px solid var(--border)', fontSize: 14, background: a.is_correct ? '#ecfdf5' : '#fff' }} />
                        </div>
                      ))}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
                    <button className="btn btn-danger" onClick={() => deleteQuestion(q.id)}
                      style={{ padding: '8px 16px', fontSize: 13 }}>
                      Удалить
                    </button>
                    <button className="btn btn-primary" onClick={() => saveQuestion(q)}
                      disabled={savingId === q.id}
                      style={{ padding: '8px 16px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Save size={14} strokeWidth={1.5} />
                      {savingId === q.id ? 'Сохранение...' : 'Сохранить'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}