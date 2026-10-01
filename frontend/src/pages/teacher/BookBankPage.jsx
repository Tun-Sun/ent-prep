import { useState, useEffect } from 'react'
import { questionsAPI, subjectsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import { BookOpen, AlertTriangle, HelpCircle } from 'lucide-react'

// зеркалит QuestionPagination на бэкенде: менять надо вместе с ним
const PAGE_SIZE = 50

const chip = (bg, color) => ({
  padding: '2px 8px', borderRadius: 100, fontSize: 11, fontWeight: 600, background: bg, color,
})

export default function BookBankPage() {
  const [rows, setRows] = useState([])
  const [subjects, setSubjects] = useState([])
  const [topics, setTopics] = useState([])
  const [filterSubject, setFilterSubject] = useState('')
  const [filterTopic, setFilterTopic] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  useEffect(() => {
    subjectsAPI.list().then(res => setSubjects(res.data))
  }, [])

  useEffect(() => {
    if (filterSubject) subjectsAPI.topics(filterSubject).then(res => setTopics(res.data))
    else setTopics([])
  }, [filterSubject])

  const load = (pg = 1) => {
    setLoading(true)
    const params = { source_type: 'book_scan', page: pg }
    if (filterSubject) params.subject = filterSubject
    if (filterTopic) params.topic = filterTopic
    if (filterStatus) params.verification_status = filterStatus
    questionsAPI.list(params)
      .then(res => { setRows(res.data.results || []); setTotal(res.data.count || 0) })
      .finally(() => setLoading(false))
  }

  useEffect(() => { setPage(1); load(1) }, [filterSubject, filterTopic, filterStatus])

  const goPage = (pg) => { setPage(pg); load(pg) }

  const sel = {
    height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px',
    fontSize: 13, background: '#fff', cursor: 'pointer', maxWidth: 260,
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title"><BookOpen size={18} strokeWidth={1.5} style={{ verticalAlign: -3, marginRight: 6 }} />Book bank</h1>
        <p className="page-subtitle">
          Problems digitized from book scans: KaTeX formulas, source page, proofreading status.
          Nothing is edited here — fix it on the digitization stand, then overwrite into the database.
        </p>
      </div>

      <div className="card" style={{ padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <select value={filterSubject} onChange={e => { setFilterSubject(e.target.value); setFilterTopic('') }} style={sel}>
            <option value="">All subjects</option>
            {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
          </select>
          <select value={filterTopic} onChange={e => setFilterTopic(e.target.value)} disabled={!filterSubject} style={sel}>
            <option value="">All topics</option>
            {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={sel}>
            <option value="">Any proofreading status</option>
            <option value="draft">Draft — nobody has checked it</option>
            <option value="verified">Verified on the stand</option>
          </select>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>
          Total: {total} · on page {rows.length}
        </div>
        {loading ? (
          <div className="text-center py-4"><div className="spinner"></div></div>
        ) : rows.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>
            <HelpCircle size={40} strokeWidth={1.5} style={{ opacity: 0.3, marginBottom: 12 }} />
            <p>No digitized problem matches this filter.</p>
          </div>
        ) : rows.map(q => {
          const pr = q.provenance || {}
          return (
            <div key={q.id} style={{ padding: '18px 20px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                <span style={chip('rgba(99,102,241,0.08)', 'var(--primary)')}>{q.subject_name}</span>
                <span style={chip('rgba(16,185,129,0.08)', '#065F46')}>{q.topic_name}</span>
                <span style={chip('rgba(245,158,11,0.1)', '#92400E')}>
                  {pr.unit || 'unit'} {pr.page ? `· p. ${pr.page}` : ''}
                </span>
                <span style={chip(q.verification_status === 'verified' ? 'rgba(16,185,129,0.12)' : 'rgba(107,114,128,0.12)',
                                  q.verification_status === 'verified' ? '#065F46' : '#374151')}>
                  {q.verification_status === 'verified' ? 'verified' : 'draft'}
                </span>
                {(q.uncertain || []).length > 0 && (
                  <span style={chip('rgba(239,68,68,0.1)', '#991B1B')}>
                    <AlertTriangle size={11} strokeWidth={1.5} style={{ verticalAlign: -1 }} /> {q.uncertain.length} uncertain signs
                  </span>
                )}
              </div>
              <div style={{ fontSize: 14, marginBottom: 10 }}>
                <FormattedText text={q.latex || q.text} markdown />
              </div>
              {q.image && (
                <div style={{ margin: '8px 0' }}>
                  <img src={q.image} alt="" style={{ maxWidth: '100%', maxHeight: 260, borderRadius: 8 }} />
                </div>
              )}
              {q.latex_answer ? (
                <div style={{ fontSize: 14 }}>
                  <b style={{ fontSize: 12, color: 'var(--text-secondary)' }}>ANSWER: </b>
                  <FormattedText text={q.latex_answer} markdown />
                </div>
              ) : (
                // без этой строки пустой ответ читается как потеря при оцифровке,
                // хотя в источнике ответа нет: у Примера разбор и есть итог
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  No answer printed in the source.
                </div>
              )}
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6 }}>
                {pr.run}{pr.model ? ` · ${pr.model}` : ''}{pr.src_sha256 ? ` · источник ${String(pr.src_sha256).slice(0, 8)}` : ''}
              </div>
            </div>
          )
        })}
        {!loading && pages > 1 && (
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '14px 20px', borderTop: '1px solid var(--border)' }}>
            <button className="btn btn-outline" disabled={page <= 1} onClick={() => goPage(page - 1)}
              style={{ borderRadius: 10, padding: '6px 14px' }}>← prev</button>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>page {page} of {pages}</span>
            <button className="btn btn-outline" disabled={page >= pages} onClick={() => goPage(page + 1)}
              style={{ borderRadius: 10, padding: '6px 14px' }}>next →</button>
          </div>
        )}
      </div>
    </div>
  )
}
