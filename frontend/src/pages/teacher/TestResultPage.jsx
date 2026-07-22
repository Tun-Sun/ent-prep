import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Printer } from 'lucide-react'
import { testsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'

export default function TestResultPage() {
  const { sessionId } = useParams()
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    testsAPI.teacherResult(sessionId)
      .then(res => setResult(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (!result) return <div className="alert alert-error">Не удалось загрузить результат</div>

  const scoreClass = result.score_percent >= 70 ? 'success' : result.score_percent >= 40 ? 'warning' : 'danger'
  const wrongCount = result.total_questions - result.correct_answers

  return (
    <div className="test-result-page">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Результаты теста</h1>
          <p className="page-subtitle">
            {result.student_name || result.student_username} &mdash; {result.subject_name}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-outline" onClick={() => window.print()}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px' }}>
            <Printer size={16} strokeWidth={1.5} />
            PDF
          </button>
        </div>
      </div>

      <div className="result-card">
        <div className={`result-card-accent ${scoreClass}`} />
        <div className="result-card-body">
          <div className="result-card-top">
            <div className={`result-card-score ${scoreClass}`}>{result.score_percent}<span className="result-card-score-pct">%</span></div>
            <div className="result-card-labels">
              <div className="result-card-label">
                {result.score_percent >= 90 ? 'Превосходно!' : result.score_percent >= 70 ? 'Отлично!' : result.score_percent >= 50 ? 'Неплохо' : result.score_percent >= 30 ? 'Можно лучше' : 'Нужно подтянуть'}
              </div>
              <div className="result-card-sub">{result.subject_name}</div>
            </div>
          </div>
          <div className="result-card-divider" />
          <div className="result-card-stats">
            <div className="result-card-stat">
              <div className="result-card-stat-value" style={{ color: 'var(--success)' }}>{result.correct_answers}</div>
              <div className="result-card-stat-label">Правильных</div>
            </div>
            <div className="result-card-stat">
              <div className="result-card-stat-value" style={{ color: 'var(--danger)' }}>{wrongCount}</div>
              <div className="result-card-stat-label">Неправильных</div>
            </div>
            <div className="result-card-stat">
              <div className="result-card-stat-value">{result.total_questions}</div>
              <div className="result-card-stat-label">Всего</div>
            </div>
          </div>
        </div>
      </div>

      <div className="card mt-4">
        <div className="card-header">{wrongCount > 0 ? `Разбор ответов (${wrongCount} ошибок)` : 'Разбор ответов'}</div>
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
                  ✗ Ответ ученика: <FormattedText text={ans.selected_answer_text} />
                </div>
                <div className="review-correct">
                  ✓ Правильный ответ: <FormattedText text={ans.correct_answer_text} />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="text-center mt-8" style={{ marginBottom: 32 }}>
        <Link to="/teacher/tests" className="btn btn-primary">К списку тестов</Link>
      </div>

      {/* Print styles */}
      <style>{`
        @media print {
          .sidebar, .mobile-tabbar, .sidebar-footer, .btn, .page-header button,
          .review-ai button, .review-wrong + .review-correct + div button,
          .mt-8 a { display: none !important; }
          .test-result-page { padding: 0 !important; }
          .card { box-shadow: none !important; border: 1px solid #ddd !important; break-inside: avoid; }
          .review-item { break-inside: avoid; page-break-inside: avoid; }
          .result-header { text-align: center; }
          body { background: #fff !important; }
        }
      `}</style>
    </div>
  )
}
