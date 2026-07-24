import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Printer, ArrowLeft, CheckCircle2, XCircle } from 'lucide-react'
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

  const scoreClass = result.score_percent >= 70 ? '#16a34a' : result.score_percent >= 40 ? '#d97706' : '#dc2626'
  const wrongCount = result.total_questions - result.correct_answers
  const gradeText = result.score_percent >= 90 ? 'Превосходно!' : result.score_percent >= 70 ? 'Отлично!' : result.score_percent >= 50 ? 'Неплохо' : result.score_percent >= 30 ? 'Можно лучше' : 'Нужно подтянуть'

  return (
    <div className="test-result-page" style={{ maxWidth: 680, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 800, color: 'var(--text)', margin: 0 }}>Результаты теста</h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 4 }}>
            {result.student_name || result.student_username} — {result.subject_name}
          </p>
        </div>
        <button className="btn btn-outline" onClick={() => window.print()}
          style={{ borderRadius: 12, display: 'flex', alignItems: 'center', gap: 6, padding: '10px 18px' }}>
          <Printer size={16} strokeWidth={1.5} />
          PDF
        </button>
      </div>

      <div className="result-card">
        <div className="result-card-accent" style={{ background: scoreClass }} />
        <div className="result-card-body" style={{ padding: '32px 36px' }}>
          <div className="result-card-top">
            <div className="result-card-score" style={{ color: scoreClass }}>
              {result.score_percent}<span className="result-card-score-pct">%</span>
            </div>
            <div className="result-card-labels">
              <div className="result-card-label" style={{ fontSize: 20 }}>{gradeText}</div>
              <div className="result-card-sub">{result.subject_name}</div>
            </div>
          </div>
          <div className="result-card-divider" />
          <div className="result-card-stats">
            <div className="result-card-stat">
              <div className="result-card-stat-value" style={{ color: '#16a34a' }}>{result.correct_answers}</div>
              <div className="result-card-stat-label">Правильных</div>
            </div>
            <div className="result-card-stat">
              <div className="result-card-stat-value" style={{ color: '#dc2626' }}>{wrongCount}</div>
              <div className="result-card-stat-label">Неправильных</div>
            </div>
            <div className="result-card-stat">
              <div className="result-card-stat-value" style={{ color: 'var(--text)' }}>{result.total_questions}</div>
              <div className="result-card-stat-label">Всего</div>
            </div>
          </div>
        </div>
      </div>

      <div className="card mt-4">
        <div className="card-header" style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          {wrongCount > 0 ? `Разбор ответов (${wrongCount} ошибок)` : 'Разбор ответов'}
        </div>
        {result.answers.map((ans, i) => {
          const Icon = ans.is_correct ? CheckCircle2 : XCircle
          const iconColor = ans.is_correct ? '#16a34a' : '#dc2626'
          return (
            <div key={ans.id} className="review-item" style={{
              padding: '18px 20px', borderBottom: '1px solid var(--border)',
            }}>
              <div className="review-question" style={{
                display: 'flex', alignItems: 'flex-start', gap: 10, fontWeight: 600, marginBottom: 10,
              }}>
                <Icon size={18} strokeWidth={2} style={{ color: iconColor, marginTop: 2, flexShrink: 0 }} />
                <span style={{ flex: 1, fontSize: 14 }}>
                  <span style={{ color: 'var(--text-secondary)', fontWeight: 500, marginRight: 6 }}>{i + 1}.</span>
                  <FormattedText text={ans.question_text} />
                </span>
              </div>
              {ans.question_image && (
                <div style={{ textAlign: 'center', margin: '8px 0 12px', marginLeft: 28 }}>
                  <img src={ans.question_image} alt="К задаче"
                    style={{ maxWidth: '100%', borderRadius: 10, maxHeight: 200, objectFit: 'contain' }} />
                </div>
              )}
              <div style={{ marginLeft: 28, fontSize: 14 }}>
                {ans.is_correct ? (
                  <div style={{ color: '#16a34a', fontWeight: 600 }}>
                    <CheckCircle2 size={14} strokeWidth={2} style={{ display: 'inline', marginRight: 6 }} />
                    <FormattedText text={ans.selected_answer_text} />
                  </div>
                ) : (
                  <div>
                    <div style={{ color: '#dc2626', fontWeight: 600, marginBottom: 4 }}>
                      <XCircle size={14} strokeWidth={2} style={{ display: 'inline', marginRight: 6 }} />
                      Ответ ученика: <FormattedText text={ans.selected_answer_text} />
                    </div>
                    <div style={{ color: '#16a34a', fontWeight: 600 }}>
                      <CheckCircle2 size={14} strokeWidth={2} style={{ display: 'inline', marginRight: 6 }} />
                      Правильный ответ: <FormattedText text={ans.correct_answer_text} />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div style={{ textAlign: 'center', marginTop: 28, marginBottom: 40 }}>
        <Link to="/teacher/tests" className="btn btn-primary"
          style={{ borderRadius: 12, padding: '10px 24px', fontWeight: 600 }}>
          К списку тестов
        </Link>
      </div>

      <style>{`
        @media print {
          .sidebar, .mobile-tabbar, .btn, .mt-8 a { display: none !important; }
          .test-result-page { padding: 0 !important; }
          .card { box-shadow: none !important; border: 1px solid #ddd !important; break-inside: avoid; }
          .review-item { break-inside: avoid; }
          body { background: #fff !important; }
        }
      `}</style>
    </div>
  )
}
