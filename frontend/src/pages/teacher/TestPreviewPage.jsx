import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { testsAPI, subjectsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'

export default function TestPreviewPage() {
  const navigate = useNavigate()
  const [subjects, setSubjects] = useState([])
  const [subjectId, setSubjectId] = useState('')
  const [numQuestions, setNumQuestions] = useState(24)
  const [filterSource, setFilterSource] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    subjectsAPI.list().then(res => setSubjects(res.data))
  }, [])

  const handleGenerate = () => {
    if (!subjectId) return
    setLoading(true)
    setError('')
    const params = { subject_id: subjectId, num_questions: numQuestions }
    if (filterSource) params.source_type = filterSource
    testsAPI.preview(params)
      .then(res => setData(res.data))
      .catch(err => setError(err.response?.data?.error || 'Ошибка загрузки'))
      .finally(() => setLoading(false))
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Просмотр теста</h1>
        <p className="page-subtitle">Сформируйте тест и отредактируйте вопросы</p>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-group" style={{ flex: 1, minWidth: 200 }}>
            <label className="form-label">Предмет</label>
            <select className="form-select" value={subjectId} onChange={e => setSubjectId(e.target.value)}>
              <option value="">Выберите предмет</option>
              {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
            </select>
          </div>
          <div className="form-group" style={{ maxWidth: 140 }}>
            <label className="form-label">Вопросов</label>
            <input
              type="number"
              className="form-input"
              value={numQuestions}
              min={1}
              max={100}
              onChange={e => setNumQuestions(Number(e.target.value))}
            />
          </div>
          <div className="form-group" style={{ maxWidth: 200 }}>
            <label className="form-label">База</label>
            <select className="form-select" value={filterSource} onChange={e => setFilterSource(e.target.value)}>
              <option value="">Все базы</option>
              <option value="collected">Собранные (ЕНТ)</option>
              <option value="authorial">Авторские</option>
            </select>
          </div>
          <button className="btn btn-primary" onClick={handleGenerate} disabled={!subjectId || loading}>
            {loading ? 'Загрузка...' : 'Сформировать'}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {data && (
        <div className="card">
          <div className="card-header">
            Всего вопросов: {data.total_questions}
          </div>
          {data.questions.map((q, i) => (
            <div key={q.id} style={{
              padding: '20px 0',
              borderBottom: '1px solid var(--border)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 15 }}>
                    {i + 1}. <FormattedText text={q.text} />
                  </div>
                  {q.image && (
                    <div style={{ textAlign: 'center', margin: '8px 0' }}>
                      <img src={q.image} alt="" style={{ maxWidth: '100%', maxHeight: 300, borderRadius: 8 }} />
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                    <span className={`badge badge-${q.difficulty}`}>
                      {q.difficulty === 'easy' ? 'Лёгкий' : q.difficulty === 'medium' ? 'Средний' : 'Сложный'}
                    </span>
                    {q.source_type === 'authorial' && <span className="badge badge-medium">Авторский</span>}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {q.answers.map(a => (
                      <div key={a.id} style={{
                        padding: '8px 12px',
                        borderRadius: 6,
                        background: a.is_correct ? '#e8f5e9' : '#f5f5f5',
                        border: a.is_correct ? '1px solid #4caf50' : '1px solid #e0e0e0',
                      }}>
                        <FormattedText text={a.text} />
                        {a.is_correct && <span style={{ color: '#2e7d32', marginLeft: 8, fontWeight: 600 }}>✓</span>}
                      </div>
                    ))}
                  </div>
                  {q.explanation && (
                    <div style={{ marginTop: 8, padding: '8px 12px', background: '#fff3e0', borderRadius: 6, fontSize: 13 }}>
                      <strong>Пояснение:</strong> <FormattedText text={q.explanation} />
                    </div>
                  )}
                </div>
                <button
                  className="btn btn-outline"
                  style={{ padding: '8px 12px', alignSelf: 'flex-start', flexShrink: 0 }}
                  title="Редактировать вопрос"
                  onClick={() => navigate(`/teacher/questions?edit=${q.id}`)}
                >
                  ✏️
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}