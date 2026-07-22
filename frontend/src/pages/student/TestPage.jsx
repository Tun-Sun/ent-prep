import { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import { testsAPI } from '../../api'
import Timer from '../../components/Timer'
import FormattedText from '../../components/FormattedText'

const LETTERS = 'ABCDEFGH'
const SECTION_LABELS = {
  history: 'История Казахстана',
  reading: 'Грамотность чтения',
  math_lit: 'Математическая грамотность',
  profile1: 'Профильный предмет 1',
  profile2: 'Профильный предмет 2',
}
const SECTION_COLORS = {
  history: '#e3f2fd',
  reading: '#e8f5e9',
  math_lit: '#fff3e0',
  profile1: '#f3e5f5',
  profile2: '#fce4ec',
}

export default function TestPage() {
  const { subjectId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const isEnt = location.pathname === '/test/ent'
  const entProfileIds = location.state || {}

  const [questions, setQuestions] = useState([])
  const [sections, setSections] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [currentIdx, setCurrentIdx] = useState(0)
  const [answers, setAnswers] = useState({})
  const [flagged, setFlagged] = useState({})
  const [dirty, setDirty] = useState({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)
  const [showGrid, setShowGrid] = useState(true)
  const [timeLimit, setTimeLimit] = useState(600)
  const [totalPoints, setTotalPoints] = useState(0)

  useEffect(() => {
    const startTest = async () => {
      try {
        let res
        if (isEnt) {
          res = await testsAPI.startEnt({
            profile1_id: entProfileIds.profile1Id,
            profile2_id: entProfileIds.profile2Id,
          })
        } else {
          res = await testsAPI.start({ subject_id: parseInt(subjectId) })
        }
        const data = res.data
        setSessionId(data.session_id)
        setQuestions(data.questions)
        setSections(data.sections || [])
        setTimeLimit(data.time_limit || 600)
        setTotalPoints(data.total_points || 0)
      } catch (err) {
        setError(err.response?.data?.error || 'Ошибка старта теста')
      } finally {
        setLoading(false)
      }
    }
    startTest()
  }, [subjectId, isEnt])

  const current = questions[currentIdx]

  const sectionForIdx = useCallback((idx) => {
    for (const s of sections) {
      if (idx + 1 >= s.start && idx + 1 <= s.end) return s
    }
    return null
  }, [sections])

  const currentSection = sectionForIdx(currentIdx)

  const answeredCount = useMemo(() => {
    let count = 0
    for (const q of questions) {
      const a = answers[q.id]
      if (!a) continue
      if (q.question_type === 'single_choice' && a) count++
      else if (q.question_type === 'multiple_choice' && a.length > 0) count++
      else if (q.question_type === 'matching') {
        const pairs = a
        if (pairs && typeof pairs === 'object' && Object.keys(pairs).length > 0) count++
      }
    }
    return count
  }, [questions, answers])

  const unansweredCount = questions.length - answeredCount

  const saveCurrentAnswers = useCallback(async () => {
    if (!sessionId) return
    const bulk = []
    for (const qId of Object.keys(dirty)) {
      if (!dirty[qId]) continue
      const a = answers[qId]
      if (qId === undefined || !a) continue
      const q = questions.find(x => x.id === parseInt(qId))
      if (!q) continue

      let payload = { question: parseInt(qId) }
      if (q.question_type === 'single_choice') {
        payload.selected_answer = a
        payload.selected_answers = [a]
      } else if (q.question_type === 'multiple_choice') {
        payload.selected_answers = a
      } else if (q.question_type === 'matching') {
        payload.matching_pairs = a
      }
      bulk.push(payload)
    }
    if (bulk.length === 0) return
    try {
      await testsAPI.answerBulk(sessionId, { answers: bulk })
      setDirty({})
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка сохранения')
    }
  }, [sessionId, answers, dirty, questions])

  useEffect(() => {
    const handle = setInterval(() => {
      if (Object.keys(dirty).length > 0) saveCurrentAnswers()
    }, 5000)
    return () => clearInterval(handle)
  }, [dirty, saveCurrentAnswers])

  const markDirty = useCallback((qId) => {
    setDirty(prev => ({ ...prev, [qId]: true }))
  }, [])

  const selectSingle = (questionId, answerId) => {
    setAnswers(prev => ({ ...prev, [questionId]: answerId }))
    markDirty(questionId)
  }

  const toggleMultiple = (questionId, answerId) => {
    setAnswers(prev => {
      const current = prev[questionId] || []
      const next = current.includes(answerId)
        ? current.filter(id => id !== answerId)
        : [...current, answerId]
      return { ...prev, [questionId]: next }
    })
    markDirty(questionId)
  }

  const setMatching = (questionId, leftId, rightId) => {
    setAnswers(prev => {
      const pairs = { ...(prev[questionId] || {}) }
      pairs[leftId] = rightId
      return { ...prev, [questionId]: pairs }
    })
    markDirty(questionId)
  }

  const toggleFlag = (questionId) => {
    setFlagged(prev => ({ ...prev, [questionId]: !prev[questionId] }))
  }

  const goToQuestion = (idx) => {
    saveCurrentAnswers()
    setCurrentIdx(idx)
  }

  const handleTimeout = () => finishTest()

  const finishTest = async () => {
    if (submitting) return
    setSubmitting(true)
    try {
      await saveCurrentAnswers()
      await testsAPI.finish(sessionId)
      navigate(`/test/result/${sessionId}`)
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка завершения теста')
    } finally {
      setSubmitting(false)
    }
  }

  const handleFinishClick = () => {
    if (unansweredCount > 0) {
      setShowConfirm(true)
    } else {
      finishTest()
    }
  }

  const dotStatus = (q, idx) => {
    if (flagged[q.id]) return 'flagged'
    if (answers[q.id]) return 'answered'
    if (idx === currentIdx) return 'current'
    return ''
  }

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (error && !questions.length) return <div className="alert alert-error">{error}</div>
  if (!current) return <div className="alert alert-error">Нет вопросов</div>

  return (
    <div className="ent-test-container">
      <div className="test-header">
        <div className="test-header-left">
          <div className="test-progress">
            {isEnt ? 'ЕНТ тест' : `Тест по предмету`} — Вопрос {currentIdx + 1} из {questions.length}
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            Отвечено: {answeredCount} / {questions.length}
            {unansweredCount > 0 && <span style={{ color: 'var(--danger)', marginLeft: 8 }}>Не отвечено: {unansweredCount}</span>}
          </div>
        </div>
        <div className="test-header-right">
          <Timer seconds={timeLimit} onTimeout={handleTimeout} isActive={!loading} sessionId={sessionId} />
          <button className="btn btn-sm btn-outline" onClick={() => setShowGrid(!showGrid)}>
            {showGrid ? 'Скрыть сетку' : 'Сетка'}
          </button>
        </div>
      </div>

      <div className="ent-layout">
        {showGrid && (
          <div className="ent-grid-sidebar">
            {sections.length > 0 && sections.map(sect => (
              <div key={sect.id} className="ent-section-block">
                <div className="ent-section-label">{sect.label}</div>
                <div className="ent-section-range">{sect.start}–{sect.end}</div>
                <div className="ent-grid">
                  {questions.slice(sect.start - 1, sect.end).map((q, i) => {
                    const idx = sect.start - 1 + i
                    return (
                      <div
                        key={q.id}
                        className={`ent-grid-dot ${dotStatus(q, idx)}`}
                        onClick={() => goToQuestion(idx)}
                        title={`Вопрос ${idx + 1}`}
                      >
                        {idx + 1}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
            {sections.length === 0 && (
              <div className="ent-grid">
                {questions.map((q, i) => (
                  <div
                    key={q.id}
                    className={`ent-grid-dot ${dotStatus(q, i)}`}
                    onClick={() => goToQuestion(i)}
                  >
                    {i + 1}
                  </div>
                ))}
              </div>
            )}
            <div className="ent-grid-legend">
              <span><span className="legend-dot answered"></span> Отвечено</span>
              <span><span className="legend-dot flagged"></span> Флаг</span>
              <span><span className="legend-dot current"></span> Текущий</span>
              <span><span className="legend-dot"></span> Нет ответа</span>
            </div>
          </div>
        )}

        <div className="ent-main-area">
          {currentSection && sections.length > 0 && (
            <div className="ent-section-header" style={{ background: SECTION_COLORS[currentSection.id] || '#f5f5f5' }}>
              <span className="ent-section-badge">{currentSection.label}</span>
              <span className="ent-section-points">Вопросы {currentSection.start}–{currentSection.end}</span>
            </div>
          )}

          <div className="question-card">
            <div className="question-meta">
              <span className="badge badge-medium">{current.topic}</span>
              <span className="badge badge-difficulty">{current.difficulty === 'easy' ? 'Базовый' : current.difficulty === 'hard' ? 'Сложный' : 'Средний'}</span>
              <span className="badge badge-points">{current.points} балл{current.points > 1 ? 'а' : ''}</span>
              <button
                className={`btn btn-sm ${flagged[current.id] ? 'btn-warning' : 'btn-outline'}`}
                onClick={() => toggleFlag(current.id)}
                style={{ marginLeft: 'auto' }}
              >
                {flagged[current.id] ? '★' : '☆'}
              </button>
            </div>
            <div className="question-text"><FormattedText text={current.text} /></div>

            {current.image && (
              <div style={{ textAlign: 'center', margin: '12px 0' }}>
                <img src={current.image} alt="К задаче" className="question-image" />
              </div>
            )}

            {current.question_type === 'single_choice' && (
              <div className="answers-list">
                {current.answers.map((ans, i) => (
                  <div
                    key={ans.id}
                    className={`answer-option ${answers[current.id] === ans.id ? 'selected' : ''}`}
                    onClick={() => selectSingle(current.id, ans.id)}
                  >
                    <div className="answer-letter">{LETTERS[i]}</div>
                    <div style={{ flex: 1 }}>
                      <FormattedText text={ans.text} />
                      {ans.image && <img src={ans.image} alt="Вариант" className="answer-image" />}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {current.question_type === 'multiple_choice' && (
              <div className="answers-list">
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>
                  Выберите все правильные варианты (отметьте галочкой)
                </div>
                {current.answers.map((ans, i) => {
                  const selected = (answers[current.id] || []).includes(ans.id)
                  return (
                    <div
                      key={ans.id}
                      className={`answer-option ${selected ? 'selected' : ''}`}
                      onClick={() => toggleMultiple(current.id, ans.id)}
                    >
                      <div className="answer-checkbox">{selected ? '✓' : ''}</div>
                      <div style={{ flex: 1 }}>
                        <FormattedText text={ans.text} />
                        {ans.image && <img src={ans.image} alt="Вариант" className="answer-image" />}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {current.question_type === 'matching' && (
              <div className="matching-container">
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>
                  Установите соответствие: выберите пару для каждого элемента
                </div>
                <div className="matching-columns">
                  <div className="matching-col">
                    {current.answers.filter(a => a.is_correct).map(ans => (
                      <div key={ans.id} className="matching-item-left">
                        <FormattedText text={ans.text} />
                      </div>
                    ))}
                  </div>
                  <div className="matching-col">
                    {current.answers.filter(a => !a.is_correct).map(ans => {
                      const pairs = answers[current.id] || {}
                      const selectedLeft = Object.entries(pairs).find(([, v]) => v === ans.id)?.[0]
                      return (
                        <div key={ans.id} className={`matching-item-right ${selectedLeft ? 'matched' : ''}`}>
                          <FormattedText text={ans.text} />
                        </div>
                      )
                    })}
                  </div>
                </div>
                <div className="matching-ui">
                  <select
                    className="form-select"
                    value=""
                    onChange={e => {
                      if (!e.target.value) return
                      const [leftId, rightId] = e.target.value.split(':')
                      setMatching(current.id, leftId, rightId)
                    }}
                  >
                    <option value="">— Соединить —</option>
                    {current.answers.filter(a => a.is_correct).map(left => {
                      const used = Object.values(answers[current.id] || {}).includes(left.id)
                      return !used ? (
                        <option key={left.id} value={`${left.id}:${left.id}`}>
                          {left.text.substring(0, 30)}...
                        </option>
                      ) : null
                    })}
                  </select>
                </div>
              </div>
            )}

            {current.question_type === 'matching' && answers[current.id] && Object.keys(answers[current.id]).length > 0 && (
              <div className="matching-pairs">
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Ваши пары:</div>
                {Object.entries(answers[current.id]).map(([leftId, rightId]) => {
                  const leftAns = current.answers.find(a => a.id === parseInt(leftId))
                  const rightAns = current.answers.find(a => a.id === parseInt(rightId))
                  if (!leftAns || !rightAns) return null
                  return (
                    <div key={leftId} className="matching-pair-row">
                      <span className="matching-pair-left">{leftAns.text.substring(0, 40)}</span>
                      <span className="matching-arrow">→</span>
                      <span className="matching-pair-right">{rightAns.text.substring(0, 40)}</span>
                      <button className="btn btn-sm btn-outline" onClick={() => {
                        setAnswers(prev => {
                          const pairs = { ...(prev[current.id] || {}) }
                          delete pairs[leftId]
                          return { ...prev, [current.id]: pairs }
                        })
                        markDirty(current.id)
                      }}>✕</button>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div className="test-nav">
            <button
              className="btn btn-outline"
              disabled={currentIdx === 0}
              onClick={() => goToQuestion(currentIdx - 1)}
            >← Назад</button>

            {currentIdx < questions.length - 1 ? (
              <button className="btn btn-primary" onClick={() => goToQuestion(currentIdx + 1)}>
                Далее →
              </button>
            ) : (
              <button className="btn btn-success" onClick={handleFinishClick} disabled={submitting}>
                {submitting ? 'Завершение...' : 'Завершить тест ✓'}
              </button>
            )}
          </div>
        </div>
      </div>

      {showConfirm && (
        <div className="modal-overlay" onClick={() => setShowConfirm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>Завершить тест?</h3>
            <p>У вас осталось неотвеченных вопросов: <strong>{unansweredCount}</strong></p>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Неотвеченные вопросы будут засчитаны как неправильные.
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button className="btn btn-outline" onClick={() => setShowConfirm(false)}>Продолжить</button>
              <button className="btn btn-success" onClick={() => { setShowConfirm(false); finishTest() }}>
                Завершить
              </button>
            </div>
          </div>
        </div>
      )}

      {error && <div className="alert alert-error" style={{ position: 'fixed', bottom: 16, right: 16 }}>{error}</div>}
    </div>
  )
}