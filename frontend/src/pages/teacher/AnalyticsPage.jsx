import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell
} from 'recharts'
import { dashboardAPI } from '../../api'

const COLORS = ['#EF4444', '#F59E0B', '#4F46E5', '#10B981', '#8B5CF6']

export default function AnalyticsPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    dashboardAPI.teacherAnalytics()
      .then(res => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>
  if (!data) return <div className="alert alert-error">Не удалось загрузить аналитику</div>

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Аналитика</h1>
        <p className="page-subtitle">Подробная статистика по тестам</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Распределение баллов */}
        <div className="card">
          <div className="card-header">Распределение баллов</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data.score_distribution || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="range" stroke="#6B7280" fontSize={12} />
              <YAxis stroke="#6B7280" fontSize={12} />
              <Tooltip formatter={(value) => [`${value} тестов`, 'Количество']} />
              <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                {(data.score_distribution || []).map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Динамика по дням */}
        <div className="card">
          <div className="card-header">Динамика среднего балла</div>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data.daily_progress || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="date" stroke="#6B7280" fontSize={12} />
              <YAxis domain={[0, 100]} stroke="#6B7280" fontSize={12} />
              <Tooltip
                formatter={(value, name) => [
                  name === 'avg_score' ? `${value}%` : value,
                  name === 'avg_score' ? 'Средний балл' : 'Тестов',
                ]}
              />
              <Line type="monotone" dataKey="avg_score" stroke="#4F46E5" strokeWidth={2} dot={{ r: 4 }} />
              <Line type="monotone" dataKey="count" stroke="#10B981" strokeWidth={2} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Итого */}
      <div className="card mt-4">
        <div className="card-header">Сводная статистика</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 20 }}>
          {(data.score_distribution || []).map((item, i) => (
            <div key={i} style={{
              padding: 20,
              borderRadius: 12,
              background: COLORS[i] + '15',
              textAlign: 'center',
            }}>
              <div style={{ fontSize: 32, fontWeight: 800, color: COLORS[i] }}>{item.count}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                тестов ({item.range})
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
