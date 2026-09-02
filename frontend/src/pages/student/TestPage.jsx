import { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import { testsAPI } from '../../api'
import Timer from '../../components/Timer'
import FormattedText from '../../components/FormattedText'
import { ChevronLeft, ChevronRight, Flag, CheckCircle, Circle, Grid3X3, X, AlertTriangle } from 'lucide-react'

const LETTERS = 'ABCDEFGH'
const SECTION_LABELS = {
  history: 'История Казахстана',
  reading: 'Грамотность чтения',
  math_lit: 'Математическая грамотность',
  profile1: 'Профильный предмет 1',
  profile2: 'Профильный предмет 2',
}

export default function TestPage() {
  const { subjectId, duelId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const isEnt = location.pathname === '/test/ent'
  const isRush = location.pathname === '/test/rush'
  const isDuel = location.pathname.startsWith('/test/duel/')
  const entProfileIds = location.state || {}
  const topicIds = location.state?.topicIds || []

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
        } else if (isRush) {
          res = await testsAPI.start({ mode: 'rush' })
        } else if (isDuel) {
          res = await testsAPI.startDuel(duelId)
          if (res.data?.already_completed) {
            navigate('/duels', { replace: true })
            return
          }
        } else {
          const payload = { subject_id: parseInt(subjectId) }
          if (topicIds.length > 0) payload.topic_ids = topicIds
          res = await testsAPI.start(payload)
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
  }, [subjectId, isEnt, isRush, isDuel, duelId])

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
  const progressPct = questions.length > 0 ? (answeredCount / questions.length) * 100 : 0

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
      if (!current.includes(answerId) && current.length >= 2) {
        setError('Можно выбрать максимум 2 варианта')
        return prev
      }
      const next = current.includes(answerId)
        ? current.filter(id => id !== answerId)
        : [...current, answerId]
      return { ...prev, [questionId]: next }
    })
    markDirty(questionId)
  }

  const setMatching = (questionId, leftId, rightText) => {
    setAnswers(prev => {
      const pairs = { ...(prev[questionId] || {}) }
      if (rightText) pairs[leftId] = rightText
      else delete pairs[leftId]
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
      if (isDuel) {
        navigate('/duels', { replace: true })
      } else {
        navigate(`/test/result/${sessionId}`)
      }
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
      <div className="test-header" style={{ padding: '14px 20px', borderRadius: 'var(--radius)', marginBottom: 16 }}>
        <div className="test-header-left">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>
              {isEnt ? 'ЕНТ симуляция' : isRush ? '⚡ Question Rush' : isDuel ? '⚔️ Дуэль' : 'Тренировка'}
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 500 }}>
              Вопрос {currentIdx + 1} из {questions.length}
            </span>
          </div>
          <div style={{ marginTop: 6, width: 200, height: 4, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
            <div style={{ width: `${progressPct}%`, height: '100%', background: 'var(--primary)', borderRadius: 4, transition: 'width 0.3s' }} />
          </div>
        </div>
        <div className="test-header-right">
          <button
            className={`btn btn-sm ${flagged[current.id] ? 'btn-warning' : 'btn-outline'}`}
            onClick={() => toggleFlag(current.id)}
            style={{ borderRadius: 10, display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <Flag size={14} strokeWidth={1.5} />
            {flagged[current.id] ? 'В флаге' : 'Флаг'}
          </button>
          <Timer seconds={timeLimit} onTimeout={handleTimeout} isActive={!loading} sessionId={sessionId} />
          <button
            className="btn btn-sm btn-outline"
            onClick={() => setShowGrid(!showGrid)}
            style={{ borderRadius: 10, display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <Grid3X3 size={14} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      <div className="ent-layout" style={{ gap: 16 }}>
        {showGrid && (
          <div className="ent-grid-sidebar" style={{ width: 280, minWidth: 280 }}>
            {sections.length > 0 && sections.map(sect => {
              const sectAnswered = questions.slice(sect.start - 1, sect.end).filter(q => answers[q.id]).length
              const sectTotal = sect.end - sect.start + 1
              return (
                <div key={sect.id} style={{
                  background: 'var(--card)', borderRadius: 'var(--radius)',
                  padding: 12, marginBottom: 10, boxShadow: 'var(--shadow)',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{sect.label}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>{sectAnswered}/{sectTotal}</span>
                  </div>
                  <div style={{ height: 2, background: 'var(--border)', borderRadius: 2, marginBottom: 10 }}>
                    <div style={{
                      width: `${(sectAnswered / sectTotal) * 100}%`, height: '100%',
                      background: 'var(--primary)', borderRadius: 2, transition: 'width 0.3s',
                    }} />
                  </div>
                  <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 4,
                  }}>
                    {questions.slice(sect.start - 1, sect.end).map((q, i) => {
                      const idx = sect.start - 1 + i
                      const st = dotStatus(q, idx)
                      return (
                        <div key={q.id} onClick={() => goToQuestion(idx)}
                          title={`Вопрос ${idx + 1}`}
                          style={{
                            aspectRatio: '1', display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 11, fontWeight: 600, borderRadius: 6, cursor: 'pointer',
                            border: st === 'current' ? '2px solid var(--primary)' : '1px solid var(--border)',
                            background: st === 'answered' ? 'var(--success)' : st === 'flagged' ? 'var(--warning)' : 'var(--bg)',
                            color: st === 'answered' || st === 'flagged' ? '#fff' : 'var(--text)',
                            boxShadow: st === 'current' ? '0 0 0 2px rgba(36,59,130,0.12)' : 'none',
                            transition: 'all 0.15s',
                          }}
                        >
                          {st === 'answered' ? <CheckCircle size={12} strokeWidth={2} /> :
                           st === 'flagged' ? <Flag size={11} strokeWidth={2} /> :
                           idx + 1}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
            {sections.length === 0 && (
              <div style={{
                background: 'var(--card)', borderRadius: 'var(--radius)',
                padding: 12, marginBottom: 10, boxShadow: 'var(--shadow)',
              }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 4 }}>
                  {questions.map((q, i) => {
                    const st = dotStatus(q, i)
                    return (
                      <div key={q.id} onClick={() => goToQuestion(i)}
                        style={{
                          aspectRatio: '1', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 11, fontWeight: 600, borderRadius: 6, cursor: 'pointer',
                          border: st === 'current' ? '2px solid var(--primary)' : '1px solid var(--border)',
                          background: st === 'answered' ? 'var(--success)' : st === 'flagged' ? 'var(--warning)' : 'var(--bg)',
                          color: st === 'answered' || st === 'flagged' ? '#fff' : 'var(--text)',
                          transition: 'all 0.15s',
                        }}
                      >
                        {st === 'answered' ? <CheckCircle size={12} strokeWidth={2} /> :
                         st === 'flagged' ? <Flag size={11} strokeWidth={2} /> :
                         i + 1}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
            <div style={{
              display: 'flex', flexWrap: 'wrap', gap: 8, fontSize: 11,
              color: 'var(--text-secondary)', padding: 10,
              background: 'var(--card)', borderRadius: 'var(--radius)', boxShadow: 'var(--shadow)',
            }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: 'var(--success)', display: 'inline-block' }} /> Отвечено
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: 'var(--warning)', display: 'inline-block' }} /> Флаг
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, border: '2px solid var(--primary)', display: 'inline-block' }} /> Текущий
              </span>
            </div>
          </div>
        )}

        <div className="ent-main-area" style={{ minWidth: 0, flex: 1 }}>
          {currentSection && sections.length > 0 && (
            <div style={{
              padding: '8px 14px', borderRadius: 'var(--radius)', marginBottom: 12,
              background: 'rgba(36,59,130,0.04)', display: 'flex', alignItems: 'center', gap: 10,
              fontSize: 13,
            }}>
              <span style={{ fontWeight: 700, color: 'var(--primary)' }}>{currentSection.label}</span>
              <span style={{ color: 'var(--text-secondary)' }}>·</span>
              <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                Вопросы {currentSection.start}–{currentSection.end}
              </span>
            </div>
          )}

          <div className="question-card" style={{ padding: '28px 32px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <span style={{
                padding: '3px 10px', borderRadius: 100, fontSize: 11, fontWeight: 600,
                background: current.difficulty === 'easy' ? 'rgba(16,185,129,0.1)' :
                            current.difficulty === 'hard' ? 'rgba(239,68,68,0.1)' :
                            'rgba(245,158,11,0.1)',
                color: current.difficulty === 'easy' ? '#065F46' :
                       current.difficulty === 'hard' ? '#991B1B' : '#92400E',
              }}>
                {current.topic}
              </span>
              <span style={{
                padding: '3px 10px', borderRadius: 100, fontSize: 11, fontWeight: 600,
                background: 'rgba(99,102,241,0.08)', color: 'var(--primary)',
              }}>
                {current.points} балл{current.points > 1 ? 'а' : ''}
              </span>
            </div>

            <div className="question-text" style={{ fontSize: 17, marginBottom: 24, lineHeight: 1.55, color: 'var(--text)' }}>
              <FormattedText text={current.text} />
            </div>

            {current.image && (
              <div style={{ textAlign: 'center', margin: '12px 0 20px' }}>
                <img src={current.image} alt="К задаче" className="question-image"
                  style={{ maxWidth: '100%', borderRadius: 12, maxHeight: 300, objectFit: 'contain' }} />
              </div>
            )}

            {current.question_type === 'single_choice' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {current.answers.map((ans, i) => {
                  const sel = answers[current.id] === ans.id
                  return (
                    <div key={ans.id} onClick={() => selectSingle(current.id, ans.id)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px',
                        borderRadius: 12, cursor: 'pointer', transition: 'all 0.15s',
                        border: sel ? '1.5px solid var(--primary)' : '1.5px solid var(--border)',
                        background: sel ? 'rgba(36,59,130,0.04)' : '#fff',
                      }}>
                      <div style={{
                        width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 13, fontWeight: 700,
                        background: sel ? 'var(--primary)' : 'var(--bg)',
                        color: sel ? '#fff' : 'var(--text-secondary)',
                        border: sel ? 'none' : '1.5px solid var(--border)',
                      }}>{LETTERS[i]}</div>
                      <div style={{ flex: 1, fontSize: 15, lineHeight: 1.4 }}>
                        <FormattedText text={ans.text} />
                        {ans.image && <img src={ans.image} alt="Вариант" className="answer-image"
                          style={{ maxWidth: '100%', borderRadius: 8, marginTop: 8, maxHeight: 150, objectFit: 'contain' }} />}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {current.question_type === 'multiple_choice' && (
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <AlertTriangle size={12} strokeWidth={1.5} />
                  Выберите не более 2 вариантов
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {current.answers.map((ans, i) => {
                    const selected = (answers[current.id] || []).includes(ans.id)
                    return (
                      <div key={ans.id} onClick={() => toggleMultiple(current.id, ans.id)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px',
                          borderRadius: 12, cursor: 'pointer', transition: 'all 0.15s',
                          border: selected ? '1.5px solid var(--primary)' : '1.5px solid var(--border)',
                          background: selected ? 'rgba(36,59,130,0.04)' : '#fff',
                        }}>
                        <div style={{
                          width: 24, height: 24, borderRadius: 6, flexShrink: 0,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 12, fontWeight: 700,
                          background: selected ? 'var(--primary)' : 'var(--bg)',
                          color: selected ? '#fff' : 'transparent',
                          border: selected ? 'none' : '1.5px solid var(--border)',
                        }}>
                          {selected ? '✓' : ''}
                        </div>
                        <div style={{ flex: 1, fontSize: 15, lineHeight: 1.4 }}>
                          <FormattedText text={ans.text} />
                          {ans.image && <img src={ans.image} alt="Вариант" className="answer-image"
                            style={{ maxWidth: '100%', borderRadius: 8, marginTop: 8, maxHeight: 150, objectFit: 'contain' }} />}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {current.question_type === 'matching' && (
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <AlertTriangle size={12} strokeWidth={1.5} />
                  Установите соответствие
                </div>
                <div style={{
                  border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 16,
                }}>
                  {current.answers.map(left => (
                    <div key={left.id}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0',
                      }}>
                      <span style={{
                        flex: 1, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>{left.text.split(' → ')[0]}</span>
                      <span style={{ color: 'var(--primary)', fontWeight: 700, flexShrink: 0 }}>→</span>
                      <select
                        value={(answers[current.id] || {})[left.id] || ''}
                        onChange={e => setMatching(current.id, left.id, e.target.value)}
                        style={{
                          flex: 1, padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border)',
                          fontSize: 13, background: '#fff', cursor: 'pointer',
                        }}
                      >
                        <option value="">— Выберите —</option>
                        {(current.matching_options || []).map(right => (
                          <option key={right} value={right}>{right}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>

                {answers[current.id] && Object.keys(answers[current.id]).length > 0 && (
                  <div style={{ marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>Ваши пары:</div>
                    {Object.entries(answers[current.id]).map(([leftId, rightId]) => {
                      const leftAns = current.answers.find(a => a.id === parseInt(leftId))
                      if (!leftAns) return null
                      return (
                        <div key={leftId} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', fontSize: 13 }}>
                          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {leftAns.text.substring(0, 40)}
                          </span>
                          <span style={{ color: 'var(--primary)', fontWeight: 700, flexShrink: 0 }}>→</span>
                          <span style={{ flex: 1, color: 'var(--primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {rightId.substring(0, 40)}
                          </span>
                          <button
                            onClick={() => {
                              setAnswers(prev => {
                                const pairs = { ...(prev[current.id] || {}) }
                                delete pairs[leftId]
                                return { ...prev, [current.id]: pairs }
                              })
                              markDirty(current.id)
                            }}
                            style={{
                              background: 'none', border: 'none', cursor: 'pointer',
                              color: 'var(--text-secondary)', fontSize: 14, padding: 4,
                            }}
                          >
                            <X size={14} strokeWidth={1.5} />
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="test-nav" style={{
            display: 'flex', justifyContent: 'space-between', marginTop: 16,
          }}>
            <button
              className="btn btn-outline"
              disabled={currentIdx === 0}
              onClick={() => goToQuestion(currentIdx - 1)}
              style={{ borderRadius: 12, padding: '10px 20px', display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <ChevronLeft size={16} strokeWidth={1.5} /> Назад
            </button>

            {currentIdx < questions.length - 1 ? (
              <button className="btn btn-primary" onClick={() => goToQuestion(currentIdx + 1)}
                style={{ borderRadius: 12, padding: '10px 22px', display: 'flex', alignItems: 'center', gap: 6 }}>
                Далее <ChevronRight size={16} strokeWidth={1.5} />
              </button>
            ) : (
              <button className="btn btn-success" onClick={handleFinishClick} disabled={submitting}
                style={{ borderRadius: 12, padding: '10px 22px', opacity: submitting ? 0.6 : 1 }}>
                {submitting ? 'Завершение...' : 'Завершить тест'}
              </button>
            )}
          </div>
        </div>
      </div>

      {showConfirm && (
        <div className="modal-overlay" onClick={() => setShowConfirm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}
            style={{ borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)', maxWidth: 400 }}>
            <h3 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>Завершить тест?</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 8 }}>
              Осталось неотвеченных вопросов: <strong style={{ color: 'var(--text)' }}>{unansweredCount}</strong>
            </p>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              Они будут засчитаны как неправильные.
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
              <button className="btn btn-outline" onClick={() => setShowConfirm(false)}
                style={{ borderRadius: 12, padding: '10px 20px', flex: 1 }}>Продолжить</button>
              <button className="btn btn-success" onClick={() => { setShowConfirm(false); finishTest() }}
                style={{ borderRadius: 12, padding: '10px 20px', flex: 1 }}>Завершить</button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div style={{
          position: 'fixed', bottom: 16, right: 16,
          background: '#FEF2F2', border: '1px solid #FEE2E2',
          color: '#991B1B', borderRadius: 12,
          padding: '12px 18px', fontSize: 14, fontWeight: 500,
          boxShadow: '0 8px 24px rgba(0,0,0,0.1)',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <AlertTriangle size={16} strokeWidth={1.5} style={{ color: '#EF4444', flexShrink: 0 }} />
          {error}
          <button onClick={() => setError('')}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#991B1B', marginLeft: 8, padding: 4 }}>
            <X size={14} strokeWidth={1.5} />
          </button>
        </div>
      )}
    </div>
  )
}
