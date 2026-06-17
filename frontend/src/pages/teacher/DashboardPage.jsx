import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend
} from 'recharts'
import { dashboardAPI } from '../../api'

const COLORS = ['#4F46E5', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6']

export default function TeacherDashboardPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    dashboardAPI.teacher()
      .then(res => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (!data) return <div className="alert alert-error">Не удалось загрузить данные</div>

  const pieData = (data.subject_stats || []).map(s => ({
    name: s.name,
    value: s.test_count,
    avg: s.avg_score,
  }))

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Дашборд учителя</h1>
        <p className="page-subtitle">Обзор прогресса учеников</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">👥</div>
          <div className="stat-value">{data.total_students}</div>
          <div className="stat-label">Учеников</div>
        </div>
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
          <div className="stat-icon">🏆</div>
          <div className="stat-value">{data.top_students?.[0]?.avg_score || 0}%</div>
          <div className="stat-label">Лучший ученик</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Средний балл по предметам */}
        <div className="card">
          <div className="card-header">Средний балл по предметам</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data.subject_stats || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="name" stroke="#6B7280" fontSize={12} />
              <YAxis domain={[0, 100]} stroke="#6B7280" fontSize={12} />
              <Tooltip formatter={(value) => [`${value}%`, 'Средний балл']} />
              <Bar dataKey="avg_score" fill="#4F46E5" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Распределение тестов по предметам */}
        <div className="card">
          <div className="card-header">Тесты по предметам</div>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                outerRadius={100}
                dataKey="value"
              >
                {pieData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Топ учеников */}
      {data.top_students && data.top_students.length > 0 && (
        <div className="card mt-4">
          <div className="card-header">🏆 Топ учеников</div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Место</th>
                  <th>Ученик</th>
                  <th>Средний балл</th>
                  <th>Тестов</th>
                </tr>
              </thead>
              <tbody>
                {data.top_students.map((s, i) => (
                  <tr key={s.id}>
                    <td>
                      <span style={{ fontSize: 20 }}>
                        {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i + 1}`}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600 }}>{s.full_name || s.username}</td>
                    <td>
                      <span className={`badge badge-${s.avg_score >= 70 ? 'easy' : s.avg_score >= 40 ? 'medium' : 'hard'}`}>
                        {s.avg_score}%
                      </span>
                    </td>
                    <td>{s.test_count}</td>
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
