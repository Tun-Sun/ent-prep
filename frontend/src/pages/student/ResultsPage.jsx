import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { testsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'

const SECTION_COLORS = {
  history: '#e3f2fd',
  reading: '#e8f5e9',
  math_lit: '#fff3e0',
  profile1: '#f3e5f5',
  profile2: '#fce4ec',
}

export default function ResultsPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
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

  const isEnt = result.is_ent
  const scorePercent = result.total_points > 0
    ? Math.round((result.earned_points / result.total_points) * 100)
    : result.score_percent
  const scoreClass = scorePercent >= 70 ? 'success' : scorePercent >= 40 ? 'warning' : 'danger'

  return (
    <div>
      <div className="d-card" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 20px', marginBottom: 16, cursor: 'pointer' }}
        onClick={() => navigate(-1)}>
        <span style={{ fontSize: 18, fontWeight: 700 }}>←</span>
        <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Назад</span>
      </div>
      <div className="page-header">
        <h1 className="page-title">{isEnt ? 'Результаты ЕНТ' : 'Результаты теста'}</h1>
        <p className="page-subtitle">{result.subject_name}</p>
      </div>

      <div className="result-card">
        <div className={`result-card-accent ${scoreClass}`} />
        <div className="result-card-body">
          <div className="result-card-top">
            <div className={`result-card-score ${scoreClass}`}>{scorePercent}<span className="result-card-score-pct">%</span></div>
            <div className="result-card-labels">
              <div className="result-card-label">
                {scorePercent >= 90 ? 'Превосходно!' : scorePercent >= 70 ? 'Отлично!' : scorePercent >= 50 ? 'Неплохо' : scorePercent >= 30 ? 'Можно лучше' : 'Нужно подтянуть'}
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
              <div className="result-card-stat-value" style={{ color: 'var(--danger)' }}>{result.total_questions - result.correct_answers}</div>
              <div className="result-card-stat-label">Неправильных</div>
            </div>
            <div className="result-card-stat">
              <div className="result-card-stat-value">{result.total_questions}</div>
              <div className="result-card-stat-label">Всего</div>
            </div>
            {isEnt && (
              <div className="result-card-stat">
                <div className="result-card-stat-value" style={{ color: 'var(--primary)' }}>{result.earned_points}</div>
                <div className="result-card-stat-label">Баллов</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Секции (для ЕНТ) */}
      {isEnt && result.sections && result.sections.length > 0 && (
        <div className="card mt-4">
          <div className="card-header">Результаты по секциям</div>
          <div className="sections-breakdown">
            {result.sections.map(s => {
              const pct = s.points_max > 0 ? Math.round((s.points_earned / s.points_max) * 100) : 0
              return (
                <div key={s.section} className="section-row" style={{ borderLeft: `4px solid ${SECTION_COLORS[s.section] || '#ddd'}` }}>
                  <div className="section-row-header">
                    <strong>{s.section_display}</strong>
                    {s.subject_name && <span className="badge badge-medium">{s.subject_name}</span>}
                  </div>
                  <div className="section-row-stats">
                    <span>Верно: {s.correct_answers}/{s.total_questions}</span>
                    <span>Баллы: {s.points_earned}/{s.points_max}</span>
                    <span>{pct}%</span>
                  </div>
                  <div className="progress-bar" style={{ height: 6, marginTop: 4 }}>
                    <div className="progress-fill" style={{ width: `${pct}%`, background: pct >= 70 ? 'var(--success)' : pct >= 40 ? 'var(--warning)' : 'var(--danger)' }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Разбор ответов */}
      <div className="card mt-4">
        <div className="card-header">Разбор ответов</div>
        {result.answers.map((ans, i) => (
          <div key={ans.id} className="review-item">
            <div className="review-question">
              {i + 1}. <FormattedText text={ans.question_text} />
              <span className="badge" style={{
                fontSize: 11, marginLeft: 8,
                background: ans.is_correct ? 'var(--success)' : 'var(--danger)',
                color: '#fff'
              }}>
                {ans.is_correct ? `+${ans.points_earned}` : `0/${ans.points_max}`}
              </span>
            </div>
            {ans.question_image && (
              <div style={{ textAlign: 'center', margin: '8px 0' }}>
                <img src={ans.question_image} alt="К задаче" className="question-image" />
              </div>
            )}
            {ans.question_type === 'single_choice' && (
              <div>
                {ans.is_correct ? (
                  <div className="review-correct">✓ <FormattedText text={ans.selected_answer_text} /></div>
                ) : (
                  <div>
                    <div className="review-wrong">✗ <FormattedText text={ans.selected_answer_text} /></div>
                    <div className="review-correct">✓ <FormattedText text={ans.correct_answer_text} /></div>
                  </div>
                )}
              </div>
            )}
            {ans.question_type === 'multiple_choice' && (
              <div>
                <div className="review-answer-label">Ваш ответ: {ans.selected_answer_text}</div>
                <div className="review-answer-label review-correct">Правильный: {ans.correct_answer_text}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  Баллы: {ans.points_earned}/{ans.points_max}
                </div>
              </div>
            )}
            {ans.question_type === 'matching' && (
              <div>
                <div className="review-answer-label">Ваши пары: {ans.selected_answer_text}</div>
                <div className="review-answer-label review-correct">Правильные: {ans.correct_answer_text}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  Баллы: {ans.points_earned}/{ans.points_max}
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
