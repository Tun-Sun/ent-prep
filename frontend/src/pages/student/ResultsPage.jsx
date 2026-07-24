import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { testsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import ProgressRing from '../../components/ProgressRing'
import { ArrowLeft, CheckCircle2, XCircle, HelpCircle } from 'lucide-react'

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
  const scoreClass = scorePercent >= 70 ? '#16a34a' : scorePercent >= 40 ? '#d97706' : '#dc2626'
  const gradeText = scorePercent >= 90 ? 'Превосходно!' : scorePercent >= 70 ? 'Отлично!' : scorePercent >= 50 ? 'Неплохо' : scorePercent >= 30 ? 'Можно лучше' : 'Нужно подтянуть'
  const wrongCount = result.total_questions - result.correct_answers

  return (
    <div style={{ maxWidth: 680, margin: '0 auto' }}>
      <div className="card" style={{
        display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 16px', marginBottom: 20,
        cursor: 'pointer',
      }} onClick={() => navigate(-1)}>
        <ArrowLeft size={16} strokeWidth={1.5} />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Назад</span>
      </div>

      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, color: 'var(--text)', margin: 0 }}>
          {isEnt ? 'Результаты ЕНТ' : 'Результаты теста'}
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 4 }}>{result.subject_name}</p>
      </div>

      <div className="result-card">
        <div className="result-card-accent" style={{ background: scoreClass }} />
        <div className="result-card-body" style={{ padding: '32px 36px' }}>
          <div className="result-card-top">
            <ProgressRing size={140} strokeWidth={8} progress={scorePercent} color={scoreClass} />
            <div className="result-card-labels" style={{ marginTop: 8 }}>
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
            {isEnt && (
              <div className="result-card-stat">
                <div className="result-card-stat-value" style={{ color: 'var(--primary)' }}>{result.earned_points}</div>
                <div className="result-card-stat-label">Баллов</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {isEnt && result.sections && result.sections.length > 0 && (
        <div className="card mt-4">
          <div className="card-header" style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            Результаты по секциям
          </div>
          <div className="sections-breakdown" style={{ padding: '12px 16px' }}>
            {result.sections.map(s => {
              const pct = s.points_max > 0 ? Math.round((s.points_earned / s.points_max) * 100) : 0
              const color = pct >= 70 ? '#16a34a' : pct >= 40 ? '#d97706' : '#dc2626'
              return (
                <div key={s.section} style={{
                  padding: '14px 16px', borderRadius: 'var(--radius)', marginBottom: 8,
                  background: 'var(--card)', border: '1px solid var(--border)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    <strong style={{ fontSize: 14 }}>{s.section_display}</strong>
                    {s.subject_name && (
                      <span style={{
                        padding: '2px 8px', borderRadius: 100, fontSize: 11, fontWeight: 600,
                        background: 'rgba(99,102,241,0.08)', color: 'var(--primary)',
                      }}>{s.subject_name}</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 16, fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>
                    <span>Верно: <strong style={{ color: 'var(--text)' }}>{s.correct_answers}/{s.total_questions}</strong></span>
                    <span>Баллы: <strong style={{ color: 'var(--text)' }}>{s.points_earned}/{s.points_max}</strong></span>
                    <span><strong style={{ color }}>{pct}%</strong></span>
                  </div>
                  <div style={{ height: 6, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.5s' }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="card mt-4">
        <div className="card-header" style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Разбор ответов
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
                <span style={{
                  flexShrink: 0, fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 100,
                  background: ans.is_correct ? 'rgba(22,163,74,0.1)' : 'rgba(220,38,38,0.1)',
                  color: iconColor,
                }}>
                  {ans.is_correct ? `+${ans.points_earned}` : `${ans.points_earned}/${ans.points_max}`}
                </span>
              </div>
              {ans.question_image && (
                <div style={{ textAlign: 'center', margin: '8px 0 12px' }}>
                  <img src={ans.question_image} alt="К задаче" className="question-image"
                    style={{ maxWidth: '100%', borderRadius: 10, maxHeight: 200, objectFit: 'contain' }} />
                </div>
              )}
              {ans.question_type === 'single_choice' && (
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
                        <FormattedText text={ans.selected_answer_text} />
                      </div>
                      <div style={{ color: '#16a34a', fontWeight: 600 }}>
                        <CheckCircle2 size={14} strokeWidth={2} style={{ display: 'inline', marginRight: 6 }} />
                        <FormattedText text={ans.correct_answer_text} />
                      </div>
                    </div>
                  )}
                </div>
              )}
              {ans.question_type === 'multiple_choice' && (
                <div style={{ marginLeft: 28, fontSize: 14 }}>
                  <div style={{ color: 'var(--text-secondary)', marginBottom: 4 }}>
                    <HelpCircle size={14} strokeWidth={1.5} style={{ display: 'inline', marginRight: 6 }} />
                    Ваш ответ: <FormattedText text={ans.selected_answer_text} />
                  </div>
                  <div style={{ color: '#16a34a', fontWeight: 600, marginBottom: 4 }}>
                    <CheckCircle2 size={14} strokeWidth={2} style={{ display: 'inline', marginRight: 6 }} />
                    Правильный: <FormattedText text={ans.correct_answer_text} />
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    Баллы: {ans.points_earned}/{ans.points_max}
                  </div>
                </div>
              )}
              {ans.question_type === 'matching' && (
                <div style={{ marginLeft: 28, fontSize: 14 }}>
                  <div style={{ color: 'var(--text-secondary)', marginBottom: 4 }}>
                    <span style={{ fontWeight: 600 }}>Ваши пары:</span>{' '}
                    <FormattedText text={ans.selected_answer_text} />
                  </div>
                  <div style={{ color: '#16a34a', fontWeight: 600, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600 }}>Правильные:</span>{' '}
                    <FormattedText text={ans.correct_answer_text} />
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    Баллы: {ans.points_earned}/{ans.points_max}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 28, marginBottom: 40 }}>
        <Link to="/" className="btn btn-primary" style={{ borderRadius: 12, padding: '10px 24px', fontWeight: 600 }}>На дашборд</Link>
        <Link to="/subjects" className="btn btn-outline" style={{ borderRadius: 12, padding: '10px 24px', fontWeight: 600 }}>Новый тест</Link>
      </div>
    </div>
  )
}
