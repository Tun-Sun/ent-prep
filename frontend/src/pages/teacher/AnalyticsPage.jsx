import { useState, useEffect, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell,
  ComposedChart,
} from 'recharts'
import { dashboardAPI, subjectsAPI, groupsAPI } from '../../api'
import { Search, X } from 'lucide-react'

const COLORS10 = ['#FF603B', '#FFC84A', '#4F46E5', '#10B981', '#8B5CF6', '#EC4899', '#14B8A6', '#F97316', '#6366F1', '#84CC16']
const STATUS_COLORS = { low: '#EF4444', mid: '#F59E0B', high: '#10B981' }

function statusColor(pct) {
  if (pct >= 80) return STATUS_COLORS.high
  if (pct >= 50) return STATUS_COLORS.mid
  return STATUS_COLORS.low
}

export default function AnalyticsPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [subjects, setSubjects] = useState([])
  const [groups, setGroups] = useState([])
  const [students, setStudents] = useState([])

  // Filters
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [groupId, setGroupId] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [studentSearch, setStudentSearch] = useState('')
  const [selectedStudent, setSelectedStudent] = useState(null)
  const [studentResults, setStudentResults] = useState([])
  const [showDropdown, setShowDropdown] = useState(false)

  const [page, setPage] = useState(1)
  const [sortField, setSortField] = useState('timestamp')
  const [sortDir, setSortDir] = useState('desc')

  const loadData = () => {
    setLoading(true)
    const params = { page, page_size: 20 }
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    if (groupId) params.group_id = groupId
    if (subjectId) params.subject_id = subjectId
    if (selectedStudent) params.student_id = selectedStudent.id

    dashboardAPI.teacherAnalytics(params)
      .then(res => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    subjectsAPI.list().then(res => setSubjects(Array.isArray(res.data) ? res.data : [])).catch(() => {})
    groupsAPI.list().then(res => setGroups(Array.isArray(res.data) ? res.data : [])).catch(() => {})
  }, [])

  useEffect(() => { setPage(1) }, [dateFrom, dateTo, groupId, subjectId, selectedStudent])

  useEffect(() => { loadData() }, [page, dateFrom, dateTo, groupId, subjectId, selectedStudent])

  // Student search (filter by group if selected)
  useEffect(() => {
    if (!studentSearch || studentSearch.length < 2) { setStudentResults([]); return }
    const timer = setTimeout(() => {
      groupsAPI.searchStudents(studentSearch, groupId).then(res => {
        setStudentResults(Array.isArray(res.data) ? res.data : [])
      }).catch(() => {})
    }, 300)
    return () => clearTimeout(timer)
  }, [studentSearch, groupId])

  // Sorting
  const sortedResults = useMemo(() => {
    if (!data?.results) return []
    return [...data.results].sort((a, b) => {
      let va = a[sortField], vb = b[sortField]
      if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
      return sortDir === 'asc' ? (va - vb) : (vb - va)
    })
  }, [data?.results, sortField, sortDir])

  const handleSort = (field) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(field); setSortDir('asc') }
  }

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <span style={{ marginLeft: 4, opacity: 0.3 }}>↕</span>
    return <span style={{ marginLeft: 4 }}>{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  const totalPages = data ? Math.ceil((data.total_count || 0) / (data.page_size || 20)) : 0

  const filterActive = dateFrom || dateTo || groupId || subjectId || selectedStudent

  const clearFilters = () => {
    setDateFrom(''); setDateTo(''); setGroupId(''); setSubjectId('')
    setSelectedStudent(null); setStudentSearch(''); setPage(1)
  }

  // Custom tooltip for charts
  const ChartTooltip = ({ active, payload, label }) => {
    if (!active || !payload) return null
    return (
      <div style={{ background: '#fff', border: '2px solid #1B1B1B', borderRadius: 12, padding: '10px 14px', fontSize: 13, boxShadow: '3px 3px 0 0 rgba(0,0,0,0.08)' }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>{label}</div>
        {payload.map((p, i) => (
          <div key={i} style={{ color: p.color, fontWeight: 500 }}>{p.name}: {p.value}{p.name === 'Средний балл' || p.name === 'Макс. балл' ? '%' : ''}</div>
        ))}
      </div>
    )
  }

  return (
    <div className="dashboard">
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <div style={{ width: 48, height: 48, borderRadius: 16, background: '#111', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, border: '2px solid #1B1B1B', boxShadow: '0 3px 0 0 var(--primary)' }}>
          📊
        </div>
        <h1 style={{ fontSize: 32, fontWeight: 800, color: 'var(--text)', margin: 0 }}>Аналитика</h1>
      </div>

      {/* Filter bar */}
      <div className="d-card" style={{ padding: 20, marginBottom: 20 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>С</label>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              style={{ height: 40, borderRadius: 12, border: '1.5px solid var(--border)', padding: '0 12px', fontSize: 14, background: '#fff' }} />
          </div>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>По</label>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              style={{ height: 40, borderRadius: 12, border: '1.5px solid var(--border)', padding: '0 12px', fontSize: 14, background: '#fff' }} />
          </div>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Группа</label>
            <select value={groupId} onChange={e => setGroupId(e.target.value)}
              style={{ height: 40, borderRadius: 12, border: '1.5px solid var(--border)', padding: '0 12px', fontSize: 14, background: '#fff', minWidth: 140 }}>
              <option value="">Все группы</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Предмет</label>
            <select value={subjectId} onChange={e => setSubjectId(e.target.value)}
              style={{ height: 40, borderRadius: 12, border: '1.5px solid var(--border)', padding: '0 12px', fontSize: 14, background: '#fff', minWidth: 140 }}>
              <option value="">Все предметы</option>
              {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
            </select>
          </div>
          <div style={{ position: 'relative', flex: 1, minWidth: 180 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Ученик</label>
            <div style={{ position: 'relative' }}>
              <input type="text" placeholder="Поиск ученика..." value={studentSearch}
                onChange={e => { setStudentSearch(e.target.value); setShowDropdown(true) }}
                onFocus={() => setShowDropdown(true)}
                onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
                style={{ height: 40, borderRadius: 12, border: '1.5px solid var(--border)', padding: '0 12px', paddingRight: 30, fontSize: 14, background: '#fff', width: '100%' }} />
              {selectedStudent ? (
                <X size={16} style={{ position: 'absolute', right: 10, top: 12, cursor: 'pointer', color: 'var(--text-secondary)' }}
                  onClick={() => { setSelectedStudent(null); setStudentSearch('') }} />
              ) : (
                <Search size={16} style={{ position: 'absolute', right: 10, top: 12, color: 'var(--text-secondary)' }} />
              )}
            </div>
            {showDropdown && studentSearch.length >= 2 && studentResults.length > 0 && (
              <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100, background: '#fff', border: '2px solid #1B1B1B', borderRadius: 12, marginTop: 4, maxHeight: 200, overflowY: 'auto', boxShadow: '3px 3px 0 0 rgba(0,0,0,0.08)' }}>
                {studentResults.map(st => (
                  <div key={st.id} style={{ padding: '10px 14px', cursor: 'pointer', borderBottom: '1px solid #f0f0f0', fontSize: 14 }}
                    onMouseDown={() => { setSelectedStudent(st); setStudentSearch(st.full_name || st.username); setShowDropdown(false) }}>
                    {st.full_name || st.username} <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>@{st.username}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          {filterActive && (
            <button onClick={clearFilters} style={{ height: 40, borderRadius: 12, border: '1.5px solid var(--border)', background: '#fff', padding: '0 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              <X size={14} /> Сбросить
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="text-center mt-8"><div className="spinner"></div></div>
      ) : !data ? (
        <div className="alert alert-error">Не удалось загрузить аналитику</div>
      ) : (
        <>
          {/* Stats summary */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 20 }}>
            <div className="d-card" style={{ padding: '16px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text)' }}>{data.total_count}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 600 }}>Всего тестов</div>
            </div>
            <div className="d-card" style={{ padding: '16px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#4F46E5' }}>{data.unique_students}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 600 }}>Сдавало учеников</div>
            </div>
            <div className="d-card" style={{ padding: '16px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#10B981' }}>{data.average_score}%</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 600 }}>Средний балл</div>
            </div>
            <div className="d-card" style={{ padding: '16px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#8B5CF6' }}>{data.below_average?.length || 0}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 600 }}>Ниже среднего</div>
            </div>
            <div className="d-card" style={{ padding: '16px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#FF603B' }}>{data.above_average?.length || 0}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 600 }}>Выше среднего</div>
            </div>
          </div>

          {/* Charts row */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
            {/* Combo chart: daily stats */}
            <div className="d-card" style={{ padding: 20 }}>
              <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Динамика сдачи</div>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={data.daily_stats || []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                  <XAxis dataKey="date" stroke="#6B7280" fontSize={11} />
                  <YAxis yAxisId="left" stroke="#6B7280" fontSize={11} />
                  <YAxis yAxisId="right" orientation="right" stroke="#6B7280" fontSize={11} domain={[0, 100]} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar yAxisId="left" dataKey="count" fill="#FFC84A" radius={[4, 4, 0, 0]} name="Кол. сдавших" />
                  <Line yAxisId="right" type="monotone" dataKey="avg_score" stroke="#4F46E5" strokeWidth={2} dot={{ r: 3 }} name="Средний балл" />
                  <Line yAxisId="right" type="monotone" dataKey="max_score" stroke="#10B981" strokeWidth={2} strokeDasharray="4 4" dot={{ r: 3 }} name="Макс. балл" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* Donut chart: subject distribution */}
            <div className="d-card" style={{ padding: 20 }}>
              <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Распределение по предметам</div>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie data={data.subject_distribution || []} dataKey="count" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={3}>
                    {(data.subject_distribution || []).map((_, i) => (
                      <Cell key={i} fill={COLORS10[i % COLORS10.length]} stroke="#fff" strokeWidth={2} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value, name, props) => [`${value} тестов (${props.payload.percentage}%)`, props.payload.name]} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8, justifyContent: 'center' }}>
                {(data.subject_distribution || []).map((d, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 500 }}>
                    <div style={{ width: 10, height: 10, borderRadius: 3, background: COLORS10[i % COLORS10.length] }} />
                    {d.name} <span style={{ color: 'var(--text-secondary)' }}>({d.percentage}%)</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Results table */}
          <div className="d-card" style={{ padding: 0, overflow: 'hidden', marginBottom: 20 }}>
            <div style={{ padding: '16px 20px', borderBottom: '2px solid #1B1B1B', fontSize: 16, fontWeight: 700 }}>
              Результаты тестов
              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', marginLeft: 8 }}>({data.total_count} записей)</span>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ borderBottom: '1.5px solid var(--border)', background: '#F9F9F9' }}>
                    {[
                      { key: 'timestamp', label: 'Дата' },
                      { key: 'group', label: 'Группа' },
                      { key: 'subject', label: 'Предмет' },
                      { key: 'student_name', label: 'Ученик' },
                      { key: 'max_score', label: 'Макс. балл' },
                      { key: 'score', label: 'Баллы' },
                      { key: 'score_percent', label: '%' },
                    ].map(col => (
                      <th key={col.key} onClick={() => handleSort(col.key)}
                        style={{ padding: '12px 14px', textAlign: 'left', fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap', fontSize: 13 }}>
                        {col.label}<SortIcon field={col.key} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedResults.map(r => (
                    <tr key={r.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                      <td style={{ padding: '10px 14px', whiteSpace: 'nowrap', fontSize: 13 }}>{r.timestamp}</td>
                      <td style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontSize: 13 }}>{r.group || '—'}</td>
                      <td style={{ padding: '10px 14px', fontWeight: 500 }}>{r.subject}</td>
                      <td style={{ padding: '10px 14px' }}>{r.student_name}</td>
                      <td style={{ padding: '10px 14px', textAlign: 'center' }}>{r.max_score}</td>
                      <td style={{ padding: '10px 14px', textAlign: 'center', fontWeight: 700 }}>{r.score}</td>
                      <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                        <span style={{
                          display: 'inline-block', padding: '2px 10px', borderRadius: 8,
                          background: statusColor(r.score_percent) + '18',
                          color: statusColor(r.score_percent), fontWeight: 700, fontSize: 13,
                        }}>{r.score_percent}%</span>
                      </td>
                    </tr>
                  ))}
                  {sortedResults.length === 0 && (
                    <tr><td colSpan={7} style={{ padding: 40, textAlign: 'center', color: 'var(--text-secondary)' }}>
                      Нет данных по выбранным фильтрам
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {/* Pagination */}
            {totalPages > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '14px 20px', borderTop: '1.5px solid var(--border)' }}>
                <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
                  style={{ padding: '6px 14px', borderRadius: 10, border: '1.5px solid var(--border)', background: '#fff', cursor: page <= 1 ? 'not-allowed' : 'pointer', opacity: page <= 1 ? 0.5 : 1, fontWeight: 600, fontSize: 13 }}>
                  ← Назад
                </button>
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>{page} из {totalPages}</span>
                <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
                  style={{ padding: '6px 14px', borderRadius: 10, border: '1.5px solid var(--border)', background: '#fff', cursor: page >= totalPages ? 'not-allowed' : 'pointer', opacity: page >= totalPages ? 0.5 : 1, fontWeight: 600, fontSize: 13 }}>
                  Вперед →
                </button>
                <select value={data.page_size} onChange={e => setPage(1)}
                  style={{ marginLeft: 8, height: 32, borderRadius: 10, border: '1.5px solid var(--border)', padding: '0 8px', fontSize: 13, background: '#fff' }}>
                  <option value="10">10</option>
                  <option value="20">20</option>
                  <option value="50">50</option>
                </select>
              </div>
            )}
          </div>

          {/* Below / Above average tables */}
          {data.below_average?.length > 0 && data.above_average?.length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
              <BelowAboveTable title="Ниже среднего балла" data={data.below_average} color="#EF4444" />
              <BelowAboveTable title="Выше среднего балла" data={data.above_average} color="#10B981" />
            </div>
          )}
        </>
      )}
    </div>
  )
}

function BelowAboveTable({ title, data, color }) {
  return (
    <div className="d-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '12px 16px', borderBottom: '2px solid #1B1B1B', fontSize: 14, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 10, height: 10, borderRadius: 3, background: color }} />
        {title} <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>({data.length})</span>
      </div>
      <div style={{ maxHeight: 320, overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)', background: '#F9F9F9' }}>
              <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, fontSize: 12 }}>Дата</th>
              <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, fontSize: 12 }}>Предмет</th>
              <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, fontSize: 12 }}>Ученик</th>
              <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, fontSize: 12 }}>Баллы</th>
              <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, fontSize: 12 }}>Макс</th>
            </tr>
          </thead>
          <tbody>
            {data.map(r => (
              <tr key={r.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                <td style={{ padding: '7px 12px', whiteSpace: 'nowrap' }}>{r.timestamp}</td>
                <td style={{ padding: '7px 12px', fontWeight: 500 }}>{r.subject}</td>
                <td style={{ padding: '7px 12px' }}>{r.student_name}</td>
                <td style={{ padding: '7px 12px', textAlign: 'center', fontWeight: 700 }}>{r.score}</td>
                <td style={{ padding: '7px 12px', textAlign: 'center', color: 'var(--text-secondary)' }}>{r.max_score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}