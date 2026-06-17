import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { dashboardAPI } from '../../api'
import { useAuth } from '../../context/AuthContext'

export default function StudentDashboardPage() {
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    dashboardAPI.student()
      .then(res => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (!data) return <div className="alert alert-error">Не удалось загрузить данные</div>

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Привет, {user?.full_name || user?.username}! 👋</h1>
        <p className="page-subtitle">Ваш прогресс подготовки к ЕНТ</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">📝</div>
          <div className="stat-value">{data.total_tests}</div>
          <div className="stat-label">Тестов сдано</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">📊</div>
          <div className="stat-value">{data.avg_score}%</div>
          <div className="stat-label">Средний балл</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">📚</div>
          <div className="stat-value">{data.subject_progress.length}</div>
          <div className="stat-label">Предметов</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">🏆</div>
          <div className="stat-value">
            {data.recent_tests.length > 0
              ? Math.max(...data.recent_tests.map(t => t.score))
              : 0}%
          </div>
          <div className="stat-label">Лучший результат</div>
        </div>
      </div>

      <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>Предметы</h2>
      <div className="subjects-grid">
        {data.subject_progress.map(subj => (
          <div key={subj.id} className="subject-card" onClick={() => navigate(`/test/start/${subj.id}`)}>
            <div className="subject-icon">{subj.icon}</div>
            <div className="subject-name">{subj.name}</div>
            <div className="stats-grid" style={{ gap: 12 }}>
              <div>
                <div className="subject-stat-value">{subj.tests_taken}</div>
                <div className="subject-stat-label">Тестов</div>
              </div>
              <div>
                <div className="subject-stat-value">{subj.avg_score}%</div>
                <div className="subject-stat-label">Средний балл</div>
              </div>
              <div>
                <div className="subject-stat-value">{subj.best_score}%</div>
                <div className="subject-stat-label">Лучший</div>
              </div>
            </div>
            <div className="progress-bar">
              <div
                className={`progress-fill ${subj.avg_score >= 70 ? 'success' : subj.avg_score >= 40 ? 'warning' : 'danger'}`}
                style={{ width: `${subj.avg_score}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      {data.recent_tests.length > 0 && (
        <div className="card mt-8">
          <div className="card-header">Последние результаты</div>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data.recent_tests}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="date" stroke="#6B7280" fontSize={12} />
              <YAxis domain={[0, 100]} stroke="#6B7280" fontSize={12} />
              <Tooltip
                formatter={(value) => [`${value}%`, 'Балл']}
                labelFormatter={(label) => `Дата: ${label}`}
              />
              <Line type="monotone" dataKey="score" stroke="#4F46E5" strokeWidth={2} dot={{ r: 5 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
