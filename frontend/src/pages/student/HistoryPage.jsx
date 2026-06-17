import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { testsAPI } from '../../api'

export default function HistoryPage() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    testsAPI.history()
      .then(res => setSessions(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">История тестов</h1>
        <p className="page-subtitle">Все ваши завершённые тесты</p>
      </div>

      {sessions.length === 0 ? (
        <div className="card text-center">
          <p style={{ color: 'var(--text-secondary)', marginBottom: 16 }}>Вы ещё не прошли ни одного теста</p>
          <Link to="/subjects" className="btn btn-primary">Выбрать предмет</Link>
        </div>
      ) : (
        <div className="card">
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Предмет</th>
                  <th>Дата</th>
                  <th>Вопросов</th>
                  <th>Правильных</th>
                  <th>Результат</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {sessions.map(s => (
                  <tr key={s.id}>
                    <td>{s.subject_icon} {s.subject_name}</td>
                    <td>{new Date(s.completed_at).toLocaleDateString('ru-RU')}</td>
                    <td>{s.total_questions}</td>
                    <td>{s.correct_answers}/{s.total_questions}</td>
                    <td>
                      <span className={`badge badge-${s.score_percent >= 70 ? 'easy' : s.score_percent >= 40 ? 'medium' : 'hard'}`}>
                        {s.score_percent}%
                      </span>
                    </td>
                    <td>
                      <Link to={`/test/result/${s.id}`} className="btn btn-outline" style={{ padding: '6px 12px', fontSize: 13 }}>
                        Подробности
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
