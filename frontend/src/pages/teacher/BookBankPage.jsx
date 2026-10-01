import { useState, useEffect } from 'react'
import { questionsAPI, subjectsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import { BookOpen, AlertTriangle, HelpCircle, Pencil } from 'lucide-react'

// зеркалит QuestionPagination на бэкенде: менять надо вместе с ним
const PAGE_SIZE = 50
const DIFFICULTY = [['easy', 'Лёгкий'], ['medium', 'Средний'], ['hard', 'Сложный']]
const STATUS = [['draft', 'Черновик'], ['verified', 'Проверено'], ['rejected', 'Отклонено']]

const chip = (bg, color) => ({
  padding: '2px 8px', borderRadius: 100, fontSize: 11, fontWeight: 600, background: bg, color,
})

const label = { fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }
const field = {
  width: '100%', borderRadius: 10, border: '1px solid var(--border)', padding: 10,
  fontSize: 13, fontFamily: 'ui-monospace, Consolas, monospace', background: '#fff',
  boxSizing: 'border-box', resize: 'vertical',
}
const pick = { ...field, fontFamily: 'inherit', cursor: 'pointer', height: 38, padding: '0 12px' }

function errorText(e) {
  const d = e?.response?.data
  if (!d) return e?.message || 'Сохранить не удалось'
  if (typeof d === 'string') return d
  return Object.entries(d).map(([k, v]) => `${k}: ${[].concat(v).join(', ')}`).join(' · ')
}

function EditModal({ q, onClose, onSaved }) {
  const [latex, setLatex] = useState(q.latex || '')
  const [answer, setAnswer] = useState(q.latex_answer || '')
  const [difficulty, setDifficulty] = useState(q.difficulty || 'medium')
  const [status, setStatus] = useState(q.verification_status || 'draft')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [showOriginal, setShowOriginal] = useState(false)
  const orig = (q.provenance || {}).ocr_original || {}

  const save = () => {
    setBusy(true)
    setErr('')
    questionsAPI.patchBookScan(q.id, {
      latex, latex_answer: answer, difficulty, verification_status: status,
    })
      .then(res => onSaved(res.data))
      .catch(e => setErr(errorText(e)))
      .finally(() => setBusy(false))
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}
           style={{ maxWidth: 1080, width: '94%', maxHeight: '92vh', display: 'flex', flexDirection: 'column' }}>
        <div className="modal-header">
          <h3>Правка задачи · {(q.provenance || {}).unit || 'задача'}
            {(q.provenance || {}).page ? ` · с. ${q.provenance.page}` : ''}</h3>
          <button className="btn btn-sm" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body" style={{ flex: 1, overflowY: 'auto', display: 'grid',
                                             gridTemplateColumns: 'repeat(auto-fit, minmax(min(340px, 100%), 1fr))',
                                             gap: 16, padding: '14px 20px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
            <div>
              <div style={label}>Условие (Markdown + LaTeX)</div>
              <textarea style={field} rows={14} value={latex} onChange={e => setLatex(e.target.value)} />
            </div>
            <div>
              <div style={label}>Ответ (если в источнике отдельный ответ)</div>
              <textarea style={field} rows={4} value={answer} onChange={e => setAnswer(e.target.value)} />
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={label}>Сложность</div>
                <select style={pick} value={difficulty} onChange={e => setDifficulty(e.target.value)}>
                  {DIFFICULTY.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <div style={label}>Статус вычитки</div>
                <select style={pick} value={status} onChange={e => setStatus(e.target.value)}>
                  {STATUS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
                </select>
              </div>
            </div>
            {Object.keys(orig).length > 0 && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                <button className="btn btn-sm btn-outline" onClick={() => setShowOriginal(s => !s)}>
                  {showOriginal ? 'Скрыть' : 'Как было в оцифровке'}
                </button>
                {showOriginal && (
                  <pre style={{ whiteSpace: 'pre-wrap', marginTop: 8, padding: 10, background: 'rgba(107,114,128,0.08)', borderRadius: 8 }}>
                    {orig.latex}
                    {orig.latex_answer ? `\n\nОтвет: ${orig.latex_answer}` : ''}
                  </pre>
                )}
              </div>
            )}
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={label}>Так это увидит ученик</div>
            <div style={{ border: '1px solid var(--border)', borderRadius: 10, padding: 14, background: '#fff',
                          fontSize: 14, overflowX: 'auto', overflowWrap: 'anywhere' }}>
              <FormattedText text={latex} markdown />
              <div style={{ marginTop: 12, borderTop: '1px dashed var(--border)', paddingTop: 10 }}>
                <b style={{ fontSize: 12, color: 'var(--text-secondary)' }}>ОТВЕТ: </b>
                {answer ? <FormattedText text={answer} markdown />
                        : <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>в источнике ответа нет</span>}
              </div>
            </div>
            {err && <div style={{ marginTop: 10, fontSize: 13, color: '#991B1B' }}>{err}</div>}
          </div>
        </div>
        <div className="modal-footer" style={{ borderTop: '1px solid var(--border)', padding: '14px 20px',
                                               display: 'flex', gap: 8, justifyContent: 'flex-end', alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', marginRight: 'auto' }}>
            Правка переживёт следующий импорт этого прогона: задача станет «правил человек».
          </span>
          <button className="btn btn-outline" onClick={onClose} style={{ borderRadius: 10, padding: '6px 14px' }}>Отмена</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}
                  style={{ borderRadius: 10, padding: '6px 16px' }}>{busy ? 'Сохраняю…' : 'Сохранить'}</button>
        </div>
      </div>
    </div>
  )
}

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
  const [editing, setEditing] = useState(null)
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

  const saved = (data) => {
    setRows(rs => rs.map(r => (r.id === data.id ? data : r)))
    setEditing(null)
  }

  const sel = {
    height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px',
    fontSize: 13, background: '#fff', cursor: 'pointer', maxWidth: 260,
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title"><BookOpen size={18} strokeWidth={1.5} style={{ verticalAlign: -3, marginRight: 6 }} />Банк из книг</h1>
        <p className="page-subtitle">
          Задачи, оцифрованные из сканов задачника: формулы KaTeX, страница источника, статус вычитки.
          Опечатку можно исправить здесь же кнопкой «Править» — правка не сотрётся при следующем импорте.
        </p>
      </div>

      <div className="card" style={{ padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <select value={filterSubject} onChange={e => { setFilterSubject(e.target.value); setFilterTopic('') }} style={sel}>
            <option value="">Все предметы</option>
            {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
          </select>
          <select value={filterTopic} onChange={e => setFilterTopic(e.target.value)} disabled={!filterSubject} style={sel}>
            <option value="">Все темы</option>
            {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={sel}>
            <option value="">Любой статус вычитки</option>
            <option value="draft">Черновик — никто не проверял</option>
            <option value="verified">Проверено</option>
            <option value="rejected">Отклонено</option>
          </select>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>
          Всего: {total} · на странице {rows.length}
        </div>
        {loading ? (
          <div className="text-center py-4"><div className="spinner"></div></div>
        ) : rows.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>
            <HelpCircle size={40} strokeWidth={1.5} style={{ opacity: 0.3, marginBottom: 12 }} />
            <p>Под этот фильтр оцифрованных задач нет.</p>
          </div>
        ) : rows.map(q => {
          const pr = q.provenance || {}
          return (
            <div key={q.id} style={{ padding: '18px 20px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8, alignItems: 'center' }}>
                <span style={chip('rgba(99,102,241,0.08)', 'var(--primary)')}>{q.subject_name}</span>
                <span style={chip('rgba(16,185,129,0.08)', '#065F46')}>{q.topic_name}</span>
                <span style={chip('rgba(245,158,11,0.1)', '#92400E')}>
                  {pr.unit || 'задача'}{pr.page ? ` · с. ${pr.page}` : ''}
                </span>
                <span style={chip(q.verification_status === 'verified' ? 'rgba(16,185,129,0.12)' : 'rgba(107,114,128,0.12)',
                                  q.verification_status === 'verified' ? '#065F46' : '#374151')}>
                  {(STATUS.find(([v]) => v === q.verification_status) || [, 'Черновик'])[1].toLowerCase()}
                </span>
                {pr.human_edited && (
                  <span style={chip('rgba(59,130,246,0.12)', '#1E40AF')}>правил человек</span>
                )}
                {(q.uncertain || []).length > 0 && (
                  <span style={chip('rgba(239,68,68,0.1)', '#991B1B')}>
                    <AlertTriangle size={11} strokeWidth={1.5} style={{ verticalAlign: -1 }} /> спорных знаков: {q.uncertain.length}
                  </span>
                )}
                <button className="btn btn-sm btn-outline" onClick={() => setEditing(q)}
                        style={{ marginLeft: 'auto', borderRadius: 10, padding: '4px 12px' }}>
                  <Pencil size={12} strokeWidth={1.5} style={{ verticalAlign: -1, marginRight: 4 }} />Править
                </button>
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
                  <b style={{ fontSize: 12, color: 'var(--text-secondary)' }}>ОТВЕТ: </b>
                  <FormattedText text={q.latex_answer} markdown />
                </div>
              ) : (
                // без этой строки пустой ответ читается как потеря при оцифровке,
                // хотя в источнике ответа нет: у Примера разбор и есть итог
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  В источнике ответа нет.
                </div>
              )}
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6 }}>
                {pr.run}{pr.model ? ` · ${pr.model}` : ''}{pr.src_sha256 ? ` · источник ${String(pr.src_sha256).slice(0, 8)}` : ''}
                {pr.edited_at ? ` · правка ${String(pr.edited_at).slice(0, 10)} (${pr.edited_by})` : ''}
              </div>
            </div>
          )
        })}
        {!loading && pages > 1 && (
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '14px 20px', borderTop: '1px solid var(--border)' }}>
            <button className="btn btn-outline" disabled={page <= 1} onClick={() => goPage(page - 1)}
              style={{ borderRadius: 10, padding: '6px 14px' }}>← назад</button>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>страница {page} из {pages}</span>
            <button className="btn btn-outline" disabled={page >= pages} onClick={() => goPage(page + 1)}
              style={{ borderRadius: 10, padding: '6px 14px' }}>вперёд →</button>
          </div>
        )}
      </div>

      {editing && <EditModal q={editing} onClose={() => setEditing(null)} onSaved={saved} />}
    </div>
  )
}
