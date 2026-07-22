import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { grantCalcAPI } from '../../api'

const TYPE_ICONS = {
  national: '🏛️',
  medical: '🏥',
  pedagogical: '🎓',
  technical: '⚙️',
  it: '💻',
  agro: '🌾',
  other: '📚',
}

const CHANCE_COLORS = {
  high: { bg: '#D1FAE5', text: '#065F46', label: 'Высокий шанс' },
  mid: { bg: '#FEF3C7', text: '#92400E', label: 'Реально' },
  low: { bg: '#FEE2E2', text: '#991B1B', label: 'Мало шансов' },
}

export default function GrantCalcPage() {
  const navigate = useNavigate()
  const [score, setScore] = useState(100)
  const [universities, setUniversities] = useState([])
  const [top, setTop] = useState({})
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState('all')
  const [favorites, setFavorites] = useState(() => {
    try { return JSON.parse(localStorage.getItem('grant_favs') || '[]') } catch { return [] }
  })

  const toggleFav = (name) => {
    setFavorites(prev => {
      const next = prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]
      localStorage.setItem('grant_favs', JSON.stringify(next))
      return next
    })
  }

  useEffect(() => {
    setLoading(true)
    grantCalcAPI.calculate({ score, search, uni_type: filterType })
      .then(res => {
        setUniversities(res.data.universities)
        setTop(res.data.top || {})
        setTotal(res.data.total)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [score, search, filterType])

  const bestThree = useMemo(() => {
    return [top.safe, top.realistic, top.dream].filter(Boolean)
  }, [top])

  const scorePercent = Math.min(100, Math.max(0, Math.round((score - 50) / 90 * 100)))
  const scoreColor = score >= 100 ? '#10B981' : score >= 75 ? '#F59E0B' : '#EF4444'

  return (
    <div>
      <div className="d-card" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 20px', marginBottom: 16, cursor: 'pointer' }}
        onClick={() => navigate(-1)}>
        <span style={{ fontSize: 18, fontWeight: 700 }}>←</span>
        <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Назад</span>
      </div>
      <div className="page-header">
        <h1 className="page-title">Калькулятор грантов</h1>
        <p className="page-subtitle">Узнай, на какие специальности ты проходишь с твоими баллами ЕНТ</p>
      </div>

      <div className="calc-score-card">
        <div className="calc-score-display">
          <div className="calc-score-value" style={{ color: scoreColor }}>{score}</div>
          <div className="calc-score-max">из 140</div>
        </div>
        <div className="calc-score-label">
          {score >= 110 ? 'Отличный результат! Грант обеспечен' :
           score >= 90 ? 'Хороший шанс на грант' :
           score >= 70 ? 'Можно побороться за грант' :
           'Нужно подтянуть баллы'}
        </div>
        <div className="calc-slider-container">
          <input
            type="range"
            min={50} max={140}
            value={score}
            onChange={e => setScore(parseInt(e.target.value))}
            className="calc-slider"
            style={{ '--track-color': scoreColor }}
          />
          <div className="calc-slider-labels">
            <span>50</span><span>80</span><span>110</span><span>140</span>
          </div>
        </div>
      </div>

      {bestThree.length > 0 && (
        <div className="calc-best-matches">
          <h3>Лучшие варианты</h3>
          <div className="calc-best-grid">
            {bestThree.map(u => (
              <div key={u.name} className={`calc-best-card chance-${u.chance}`}>
                <div className="calc-best-icon">{TYPE_ICONS[u.uni_type] || '🏛️'}</div>
                <div className="calc-best-info">
                  <div className="calc-best-name">{u.name}</div>
                  <div className="calc-best-city">{u.city}</div>
                  <div className="calc-best-min">Мин. балл: {u.min_score}</div>
                  <span className="calc-chance-badge" style={{
                    background: CHANCE_COLORS[u.chance].bg,
                    color: CHANCE_COLORS[u.chance].text,
                  }}>
                    {CHANCE_COLORS[u.chance].label} (+{u.gap})
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="calc-controls">
        <input
          type="text"
          className="form-input"
          placeholder="Поиск вуза, города, специальности..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      <div className="calc-filters">
        <button
          className={`btn btn-sm ${filterType === 'all' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setFilterType('all')}
        >Все</button>
        {Object.entries(TYPE_ICONS).map(([type, icon]) => (
          <button
            key={type}
            className={`btn btn-sm ${filterType === type ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => setFilterType(type)}
          >{icon} {type}</button>
        ))}
      </div>

      <div className="calc-count">
        Найдено: {total} вузов
        {favorites.length > 0 && <span className="calc-fav-count">★ {favorites.length}</span>}
      </div>

      {loading ? (
        <div className="text-center mt-8"><div className="spinner"></div></div>
      ) : (
        <div className="calc-uni-grid">
          {universities.map(u => {
            const color = CHANCE_COLORS[u.chance] || CHANCE_COLORS.low
            const isFav = favorites.includes(u.name)
            const pct = Math.min(100, Math.round(score / u.min_score * 100))
            return (
              <div key={u.id} className="calc-uni-card" style={{ borderLeftColor: color.text }}>
                <div className="calc-uni-header">
                  <span className="calc-uni-icon">{TYPE_ICONS[u.uni_type] || '🏛️'}</span>
                  <button
                    className={`calc-fav-btn ${isFav ? 'active' : ''}`}
                    onClick={() => toggleFav(u.name)}
                  >★</button>
                </div>
                <div className="calc-uni-name">{u.name}</div>
                <div className="calc-uni-meta">
                  <span>{u.city}</span>
                  <span className="calc-uni-badge" style={{ background: color.bg, color: color.text }}>
                    {color.label}
                  </span>
                </div>
                <div className="calc-uni-score-row">
                  <span>Мин. {u.min_score}</span>
                  <span>Ваш: {score}</span>
                  <span style={{ color: color.text, fontWeight: 700 }}>{u.gap > 0 ? `+${u.gap}` : u.gap}</span>
                </div>
                <div className="calc-progress-bar">
                  <div className="calc-progress-fill" style={{ width: `${pct}%`, background: color.text }} />
                </div>
                <div className="calc-uni-specs">{u.specializations}</div>
                {u.info && <div className="calc-uni-info">{u.info}</div>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}