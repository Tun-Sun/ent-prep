import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { testsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import { X, ExternalLink, Edit3 } from 'lucide-react'

export default function AuthorialTestsPage() {
  const navigate = useNavigate()
  const [tests, setTests] = useState([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [questions, setQuestions] = useState([])
  const [questionsLoading, setQuestionsLoading] = useState(false)
  const [renaming, setRenaming] = useState(null)
  const [renameValue, setRenameValue] = useState('')

  const authHeaders = { Authorization: `Bearer ${localStorage.getItem('access_token')}` }

  const load = () => {
    setLoading(true)
    testsAPI.authorialTests()
      .then(res => setTests(res.data))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleDelete = (formId) => {
    if (!confirm('Удалить этот тест и все его вопросы?')) return
    setDeleting(formId)
    testsAPI.deleteAuthorialTest(formId)
      .then(() => load())
      .catch(() => alert('Ошибка удаления'))
      .finally(() => setDeleting(null))
  }

  const handleView = (formId) => {
    setQuestionsLoading(true)
    setViewing(formId)
    testsAPI.authorialTestQuestions(formId)
      .then(res => setQuestions(res.data.questions || []))
      .catch(() => alert('Ошибка загрузки'))
      .finally(() => setQuestionsLoading(false))
  }

  const startRename = (t) => {
    setRenaming(t.form_id)
    setRenameValue(t.topic)
  }

  const saveRename = async () => {
    if (!renameValue.trim() || !renaming) return
    const t = tests.find(x => x.form_id === renaming)
    if (!t) return
    try {
      await fetch(`/api/topics/${t.topic_id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ name: renameValue.trim() }),
      })
      setRenaming(null)
      load()
    } catch { alert('Ошибка сохранения') }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Авторские тесты</h1>
        <p className="page-subtitle">Управление импортированными тестами</p>
      </div>

      <div className="card">
        <div className="card-header">Всего тестов: {tests.length}</div>
        {loading ? (
          <div className="text-center"><div className="spinner"></div></div>
        ) : tests.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 32 }}>
            Нет авторских тестов. Импортируйте через Google Forms.
          </p>
        ) : (
          tests.map(t => (
            <div key={t.form_id} style={{
              padding: '16px 0',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              {renaming === t.form_id ? (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flex: 1 }}>
                  <input className="form-input" style={{ flex: 1, maxWidth: 400 }}
                    value={renameValue} autoFocus
                    onChange={e => setRenameValue(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') saveRename()
                      if (e.key === 'Escape') setRenaming(null)
                    }} />
                  <button className="btn btn-primary btn-sm" onClick={saveRename}>OK</button>
                  <button className="btn btn-outline btn-sm" onClick={() => setRenaming(null)}>✕</button>
                </div>
              ) : (
                <div>
                  <div style={{ fontWeight: 600 }}>{t.subject} — {t.topic}</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
                    {t.count} вопросов
                  </div>
                </div>
              )}
              <div style={{ display: 'flex', gap: 8 }}>
                {renaming !== t.form_id && (
                  <button className="btn btn-outline" style={{ padding: '8px 12px' }}
                    onClick={() => startRename(t)} title="Переименовать">
                    ✏️
                  </button>
                )}
                <button
                  className="btn btn-outline"
                  style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 4 }}
                  onClick={() => handleView(t.form_id)}
                >
                  <ExternalLink size={14} strokeWidth={1.5} />
                  Посмотреть
                </button>
                <button
                  className="btn btn-danger"
                  style={{ padding: '8px 16px' }}
                  onClick={() => handleDelete(t.form_id)}
                  disabled={deleting === t.form_id}
                >
                  {deleting === t.form_id ? 'Удаление...' : 'Удалить'}
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {viewing && (
        <div className="modal-overlay" onClick={() => setViewing(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 700, maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}>
            <div className="modal-header">
              <h3>Просмотр теста</h3>
              <button className="btn btn-sm" onClick={() => setViewing(null)}><X size={16} /></button>
            </div>
            <div className="modal-body" style={{ flex: 1, overflowY: 'auto' }}>
              {questionsLoading ? (
                <div className="text-center"><div className="spinner"></div></div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  {questions.map((q, i) => (
                    <div key={q.id} style={{ padding: 16, borderRadius: 12, border: '1px solid var(--border)', background: '#fafafa' }}>
                      <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 15 }}>
                        {i + 1}. <FormattedText text={q.text} />
                      </div>
                      {q.image && (
                        <div style={{ textAlign: 'center', margin: '8px 0' }}>
                          <img src={q.image} alt="К вопросу" style={{ maxWidth: '100%', maxHeight: 200, borderRadius: 8 }} />
                        </div>
                      )}
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
                        <span className="badge badge-medium" style={{ fontSize: 11 }}>{q.difficulty === 'easy' ? 'Лёгкий' : q.difficulty === 'hard' ? 'Сложный' : 'Средний'}</span>
                        {q.explanation && <span className="badge badge-medium" style={{ fontSize: 11, background: '#e0e7ff', color: '#3730A3' }}>есть объяснение</span>}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {(q.answers || []).map(a => (
                          <div key={a.id} style={{
                            padding: '8px 12px', borderRadius: 8, fontSize: 14,
                            border: a.is_correct ? '2px solid var(--success)' : '1px solid var(--border)',
                            background: a.is_correct ? '#ecfdf5' : '#fff',
                            color: a.is_correct ? '#065f46' : 'var(--text)',
                          }}>
                            {a.is_correct ? '✓ ' : ''}<FormattedText text={a.text} />
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="modal-footer" style={{ borderTop: '1px solid var(--border)', padding: '12px 20px', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-outline" onClick={() => setViewing(null)}>Закрыть</button>
              <button className="btn btn-primary" onClick={() => { setViewing(null); navigate(`/teacher/tests/authorial/${viewing}/edit`) }}
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Edit3 size={14} strokeWidth={1.5} />
                Редактировать
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
