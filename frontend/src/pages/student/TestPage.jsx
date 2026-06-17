import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { testsAPI } from '../../api'
import Timer from '../../components/Timer'
import FormattedText from '../../components/FormattedText'

export default function TestPage() {
  const { subjectId } = useParams()
  const navigate = useNavigate()
  const [questions, setQuestions] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [currentIdx, setCurrentIdx] = useState(0)
  const [answers, setAnswers] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState({})

  // Старт теста
  useEffect(() => {
    testsAPI.start({ subject_id: parseInt(subjectId), num_questions: 10 })
      .then(res => {
        setSessionId(res.data.session_id)
        setQuestions(res.data.questions)
      })
      .catch(err => setError(err.response?.data?.error || 'Ошибка старта теста'))
      .finally(() => setLoading(false))
  }, [subjectId])

  const selectAnswer = async (questionId, answerId) => {
    if (submitted[questionId]) return

    const newAnswers = { ...answers, [questionId]: answerId }
    setAnswers(newAnswers)

    try {
      await testsAPI.answer(sessionId, { question: questionId, selected_answer: answerId })
      setSubmitted(prev => ({ ...prev, [questionId]: true }))
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка сохранения ответа')
    }
  }

  const finishTest = async () => {
    try {
      await testsAPI.finish(sessionId)
      navigate(`/test/result/${sessionId}`)
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка завершения теста')
    }
  }

  const handleTimeout = () => finishTest()

  const current = questions[currentIdx]
  const answeredCount = Object.keys(answers).length
  const letters = ['A', 'B', 'C', 'D']

  const diffLabel = { easy: 'Лёгкий', medium: 'Средний', hard: 'Сложный' }

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (error && !questions.length) return <div className="alert alert-error">{error}</div>

  return (
    <div>
      <div className="test-header">
        <div className="test-progress">
          Вопрос {currentIdx + 1} из {questions.length}
          <span className="badge badge-medium">{answeredCount} отвечено</span>
        </div>
        <Timer seconds={600} onTimeout={handleTimeout} isActive={true} />
      </div>

      <div className="progress-bar" style={{ marginBottom: 24 }}>
        <div className="progress-fill" style={{ width: `${(answeredCount / questions.length) * 100}%` }} />
      </div>

      {current && (
        <div className="question-card">
          <div className="question-meta">
            <span className="badge badge-medium">{current.topic}</span>
            <span className={`badge badge-${current.difficulty}`}>{diffLabel[current.difficulty]}</span>
          </div>
          <div className="question-text"><FormattedText text={current.text} /></div>

          {current.image && (
            <div style={{ textAlign: 'center', margin: '12px 0' }}>
              <img
                src={current.image}
                alt="К задаче"
                style={{ maxWidth: '100%', borderRadius: 8, border: '1px solid var(--border)' }}
              />
            </div>
          )}

          <div className="answers-list">
            {current.answers.map((ans, i) => (
              <div
                key={ans.id}
                className={`answer-option ${
                  answers[current.id] === ans.id ? 'selected' : ''
                } ${submitted[current.id] && answers[current.id] === ans.id ? 'selected' : ''}`}
                onClick={() => selectAnswer(current.id, ans.id)}
              >
                <div className="answer-letter">{letters[i]}</div>
                <div style={{ flex: 1 }}>
                  <FormattedText text={ans.text} />
                  {ans.image && (
                    <img
                      src={ans.image}
                      alt="Вариант"
                      style={{ maxWidth: '100%', borderRadius: 6, marginTop: 8 }}
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="test-nav">
        <button
          className="btn btn-outline"
          disabled={currentIdx === 0}
          onClick={() => setCurrentIdx(prev => prev - 1)}
        >
          ← Назад
        </button>

        {currentIdx < questions.length - 1 ? (
          <button
            className="btn btn-primary"
            onClick={() => setCurrentIdx(prev => prev + 1)}
          >
            Далее →
          </button>
        ) : (
          <button className="btn btn-success" onClick={finishTest}>
            Завершить тест ✓
          </button>
        )}
      </div>

      {/* Навигатор вопросов */}
      <div className="card mt-4">
        <div className="card-header">Навигация по вопросам</div>
        <div className="question-nav">
          {questions.map((q, i) => (
            <div
              key={q.id}
              className={`question-dot ${answers[q.id] ? 'answered' : ''} ${i === currentIdx ? 'current' : ''}`}
              onClick={() => setCurrentIdx(i)}
            >
              {i + 1}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
