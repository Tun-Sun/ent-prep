import { useState, useEffect } from 'react'
import { dashboardAPI } from '../../api'

export default function StudentsPage() {
  const [students, setStudents] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('avg_score')

  useEffect(() => {
    dashboardAPI.teacherStudents()
      .then(res => setStudents(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>

  const filtered = students
    .filter(s =>
      (s.full_name || s.username).toLowerCase().includes(search.toLowerCase()) ||
      (s.school || '').toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      if (sortBy === 'avg_score') return (b.avg_score || 0) - (a.avg_score || 0)
      if (sortBy === 'total_tests') return (b.total_tests || 0) - (a.total_tests || 0)
      return (a.full_name || a.username).localeCompare(b.full_name || b.username)
    })

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Ученики</h1>
        <p className="page-subtitle">Прогресс каждого ученика по предметам</p>
      </div>

      <div className="card">
        <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
          <input
            className="form-input"
            style={{ maxWidth: 300 }}
            placeholder="Поиск по имени или школе..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <select
            className="form-select"
            style={{ maxWidth: 200 }}
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
          >
            <option value="avg_score">По среднему баллу</option>
            <option value="total_tests">По кол-ву тестов</option>
            <option value="name">По имени</option>
          </select>
        </div>

        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Ученик</th>
                <th>Школа</th>
                <th>Тестов</th>
                <th>Средний балл</th>
                <th>Прогресс по предметам</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(s => (
                <tr key={s.id}>
                  <td style={{ fontWeight: 600 }}>{s.full_name || s.username}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{s.school || '—'}</td>
                  <td>{s.total_tests}</td>
                  <td>
                    <span className={`badge badge-${s.avg_score >= 70 ? 'easy' : s.avg_score >= 40 ? 'medium' : 'hard'}`}>
                      {s.avg_score}%
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {Object.entries(s.subject_progress || {}).map(([name, score]) => (
                        <span key={name} style={{
                          padding: '4px 10px',
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 600,
                          background: score >= 70 ? '#D1FAE5' : score >= 40 ? '#FEF3C7' : '#FEE2E2',
                          color: score >= 70 ? '#065F46' : score >= 40 ? '#92400E' : '#991B1B',
                        }}>
                          {name}: {score}%
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={5} style={{ textAlign: 'center', padding: 32, color: 'var(--text-secondary)' }}>
                  Ученики не найдены
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
