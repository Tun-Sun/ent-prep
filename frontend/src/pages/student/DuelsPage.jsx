import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { gamificationAPI, subjectsAPI } from '../../api'
import { Swords, ArrowLeft, Plus, Search, Trophy, Handshake, X, Play } from 'lucide-react'

const STATUS_COLORS = {
  pending: '#F59E0B',
  active: '#243B82',
  completed: '#10B981',
  declined: '#9CA3AF',
  expired: '#9CA3AF',
}

export default function DuelsPage() {
  const [duels, setDuels] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [opponents, setOpponents] = useState([])
  const [search, setSearch] = useState('')
  const [subjects, setSubjects] = useState([])
  const [subjectId, setSubjectId] = useState('')
  const [selectedOpponent, setSelectedOpponent] = useState(null)
  const [numQuestions, setNumQuestions] = useState(10)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const loadDuels = useCallback(() => {
    gamificationAPI.duels()
      .then(res => setDuels(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadDuels() }, [loadDuels])

  useEffect(() => {
    if (!showCreate) return
    subjectsAPI.list().then(res => {
      const list = Array.isArray(res.data) ? res.data : []
      setSubjects(list.filter(s => s.subject_type === 'profile' || s.subject_type === 'mandatory'))
    }).catch(() => {})
  }, [showCreate])

  useEffect(() => {
    if (!showCreate) return
    const t = setTimeout(() => {
      gamificationAPI.duelOpponents(search)
        .then(res => setOpponents(res.data))
        .catch(() => {})
    }, 300)
    return () => clearTimeout(t)
  }, [search, showCreate])

  const createDuel = async () => {
    if (creating) return
    setCreating(true)
    setError('')
    try {
      const payload = { num_questions: numQuestions }
      if (selectedOpponent) payload.opponent_id = selectedOpponent.id
      if (subjectId) payload.subject_id = parseInt(subjectId)
      await gamificationAPI.createDuel(payload)
      setShowCreate(false)
      setSelectedOpponent(null)
      setSearch('')
      setSubjectId('')
      loadDuels()
    } catch (err) {
      setError(err.response?.data?.error || 'Не удалось создать дуэль')
    } finally {
      setCreating(false)
    }
  }

  const respond = async (duelId, action) => {
    try {
      await gamificationAPI.respondDuel(duelId, action)
      loadDuels()
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка')
    }
  }

  const playDuel = async (duelId) => {
    navigate(`/test/duel/${duelId}`)
  }

  const StatusBadge = ({ d }) => (
    <span style={{
      padding: '4px 12px', borderRadius: 100, fontSize: 11, fontWeight: 700,
      background: `${STATUS_COLORS[d.status]}18`, color: STATUS_COLORS[d.status],
    }}>
      {d.status_display}
    </span>
  )

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      <div className="card" style={{
        display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 16px', marginBottom: 20,
        cursor: 'pointer',
      }} onClick={() => navigate(-1)}>
        <ArrowLeft size={16} strokeWidth={1.5} />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Назад</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 6 }}>
            Соревнование
          </div>
          <h1 style={{ fontSize: 28, fontWeight: 800, color: 'var(--text)', margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Swords size={26} strokeWidth={1.5} /> Дуэли
          </h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 4 }}>
            Вызывай одноклассников — одинаковые вопросы, кто точнее, тот победил
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}
          style={{ borderRadius: 12, padding: '10px 18px', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <Plus size={16} strokeWidth={2} /> Вызвать
        </button>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}

      {loading ? (
        <div className="text-center mt-8"><div className="spinner"></div></div>
      ) : duels.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 48 }}>
          <Swords size={40} strokeWidth={1.2} style={{ color: 'var(--text-secondary)', opacity: 0.5, marginBottom: 12 }} />
          <p style={{ color: 'var(--text-secondary)', margin: 0 }}>
            Пока нет дуэлей. Вызови соперника — это веселее, чем тренироваться одному!
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {duels.map(d => (
            <div key={d.id} className="card" style={{ padding: '16px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 12, flexShrink: 0,
                  background: d.status === 'completed'
                    ? (d.is_draw ? '#FEF3C7' : d.i_won ? '#D1FAE5' : '#FEE2E2')
                    : 'rgba(36,59,130,0.08)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18,
                }}>
                  {d.status === 'completed'
                    ? (d.is_draw ? '🤝' : d.i_won ? '🏆' : '💪')
                    : '⚔️'}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 8 }}>
                    {d.opponent ? d.opponent.full_name : 'Открытый вызов'}
                    <StatusBadge d={d} />
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                    {d.subject ? `${d.subject.icon} ${d.subject.name} · ` : ''}{d.num_questions} вопросов · {d.created_at}
                    {d.status === 'completed' && (
                      ` · ${d.my_score ?? '—'} : ${d.opp_score ?? '—'}`
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                  {d.can_accept && (
                    <>
                      <button className="btn btn-primary btn-sm" style={{ borderRadius: 10 }}
                        onClick={() => respond(d.id, 'accept')}>Принять</button>
                      <button className="btn btn-outline btn-sm" style={{ borderRadius: 10 }}
                        onClick={() => respond(d.id, 'decline')}>
                        <X size={14} strokeWidth={2} />
                      </button>
                    </>
                  )}
                  {d.can_play && (
                    <button className="btn btn-primary btn-sm" style={{ borderRadius: 10, display: 'flex', alignItems: 'center', gap: 6 }}
                      onClick={() => playDuel(d.id)}>
                      <Play size={13} strokeWidth={2} /> Играть
                    </button>
                  )}
                  {d.status === 'pending' && d.i_am_challenger && (
                    <button className="btn btn-outline btn-sm" style={{ borderRadius: 10 }}
                      onClick={() => respond(d.id, 'cancel')}>Отменить</button>
                  )}
                  {d.status === 'active' && d.my_done && (
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)', alignSelf: 'center' }}>
                      Ждём соперника…
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" style={{ borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-lg)', maxWidth: 480, width: '90%' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3 style={{ fontSize: 20, fontWeight: 800 }}>Вызов на дуэль</h3>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
              Выбери соперника (или оставь открытый вызов) и предмет
            </p>

            <div style={{ position: 'relative', marginBottom: 12, marginTop: 12 }}>
              <Search size={15} strokeWidth={1.5} style={{ position: 'absolute', left: 12, top: 12, color: 'var(--text-secondary)' }} />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Поиск ученика..."
                style={{
                  width: '100%', padding: '10px 12px 10px 36px', borderRadius: 12,
                  border: '1px solid var(--border)', fontSize: 14, outline: 'none',
                }}
              />
            </div>

            <div style={{ maxHeight: 180, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 12, marginBottom: 14 }}>
              <div
                onClick={() => setSelectedOpponent(null)}
                style={{
                  padding: '10px 14px', cursor: 'pointer', fontSize: 14, fontWeight: 600,
                  background: selectedOpponent === null ? 'rgba(36,59,130,0.08)' : 'transparent',
                  borderBottom: '1px solid var(--border)',
                }}>
                🌍 Открытый вызов — примет любой
              </div>
              {opponents.map(o => (
                <div
                  key={o.id}
                  onClick={() => setSelectedOpponent(o)}
                  style={{
                    padding: '10px 14px', cursor: 'pointer', fontSize: 14,
                    background: selectedOpponent?.id === o.id ? 'rgba(36,59,130,0.08)' : 'transparent',
                    borderBottom: '1px solid var(--border)',
                  }}>
                  {o.full_name} <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>@{o.username}</span>
                </div>
              ))}
              {opponents.length === 0 && (
                <div style={{ padding: 14, fontSize: 13, color: 'var(--text-secondary)', textAlign: 'center' }}>
                  Ученики не найдены
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
              <select value={subjectId} onChange={e => setSubjectId(e.target.value)}
                style={{ flex: 1, padding: '10px 12px', borderRadius: 12, border: '1px solid var(--border)', fontSize: 14, background: '#fff' }}>
                <option value="">Смешанные предметы</option>
                {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
              </select>
              <select value={numQuestions} onChange={e => setNumQuestions(parseInt(e.target.value))}
                style={{ padding: '10px 12px', borderRadius: 12, border: '1px solid var(--border)', fontSize: 14, background: '#fff' }}>
                <option value={5}>5 вопросов</option>
                <option value={10}>10 вопросов</option>
                <option value={15}>15 вопросов</option>
                <option value={20}>20 вопросов</option>
              </select>
            </div>

            <div className="modal-footer" style={{ borderTop: '1px solid var(--border)', paddingTop: 16, marginTop: 0 }}>
              <button className="btn btn-outline" onClick={() => setShowCreate(false)}
                style={{ borderRadius: 12, padding: '10px 20px' }}>Отмена</button>
              <button className="btn btn-primary" onClick={createDuel} disabled={creating}
                style={{ borderRadius: 12, padding: '10px 20px', opacity: creating ? 0.6 : 1 }}>
                {creating ? 'Создаём...' : 'Бросить вызов'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
