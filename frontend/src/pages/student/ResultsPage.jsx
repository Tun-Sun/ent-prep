import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { testsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'

export default function ResultsPage() {
  const { sessionId } = useParams()
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    testsAPI.result(sessionId)
      .then(res => setResult(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (!result) return <div className="alert alert-error">Не удалось загрузить результат</div>

  const scoreClass = result.score_percent >= 70 ? 'success' : result.score_percent >= 40 ? 'warning' : 'danger'

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Результаты теста</h1>
        <p className="page-subtitle">{result.subject_name}</p>
      </div>

      <div className="card result-header">
        <div className={`result-score ${scoreClass}`}>{result.score_percent}%</div>
        <div className="result-label">
          {result.score_percent >= 70 ? 'Отлично!' : result.score_percent >= 40 ? 'Неплохо, но можно лучше' : 'Нужно подтянуть'}
        </div>
        <div className="result-details">
          <div className="result-detail">
            <div className="result-detail-value" style={{ color: 'var(--success)' }}>
              {result.correct_answers}
            </div>
            <div className="result-detail-label">Правильных</div>
          </div>
          <div className="result-detail">
            <div className="result-detail-value" style={{ color: 'var(--danger)' }}>
              {result.total_questions - result.correct_answers}
            </div>
            <div className="result-detail-label">Неправильных</div>
          </div>
          <div className="result-detail">
            <div className="result-detail-value">{result.total_questions}</div>
            <div className="result-detail-label">Всего вопросов</div>
          </div>
        </div>
      </div>

      {/* Разбор ответов */}
      <div className="card mt-4">
        <div className="card-header">Разбор ответов</div>
        {result.answers.map((ans, i) => (
          <div key={ans.id} className="review-item">
            <div className="review-question">
              {i + 1}. <FormattedText text={ans.question_text} />
            </div>
            {ans.question_image && (
              <div style={{ textAlign: 'center', margin: '8px 0' }}>
                <img
                  src={ans.question_image}
                  alt="К задаче"
                  style={{ maxWidth: '100%', borderRadius: 8, border: '1px solid var(--border)' }}
                />
              </div>
            )}
            {ans.is_correct ? (
              <div className="review-correct">
                ✓ Верно — <FormattedText text={ans.selected_answer_text} />
              </div>
            ) : (
              <div>
                <div className="review-wrong">
                  ✗ Ваш ответ: <FormattedText text={ans.selected_answer_text} />
                </div>
                <div className="review-correct">
                  ✓ Правильный ответ: <FormattedText text={ans.correct_answer_text} />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="text-center mt-8" style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
        <Link to="/" className="btn btn-primary">На дашборд</Link>
        <Link to="/subjects" className="btn btn-outline">Новый тест</Link>
      </div>
    </div>
  )
}
