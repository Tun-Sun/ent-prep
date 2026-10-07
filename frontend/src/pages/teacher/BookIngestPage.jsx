import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { ingestAPI, subjectsAPI } from '../../api'
import { ScanText, AlertTriangle, Play, FileText } from 'lucide-react'

const LANGUAGES = [['ru', 'русский'], ['kk', 'қазақша'], ['uz', "o'zbekcha"]]
const CHIP = {
  pending: ['#EEF2FF', '#4338CA'], running: ['#FEF3C7', '#B45309'],
  done: ['#DCFCE7', '#15803D'], failed: ['#FEE2E2', '#B91C1C'],
}

const label = { fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }
const field = {
  width: '100%', borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px',
  fontSize: 13, height: 38, background: '#fff', boxSizing: 'border-box', fontFamily: 'inherit',
}
const card = {
  border: '1px solid var(--border)', borderRadius: 14, padding: 16, background: '#fff',
  marginBottom: 16,
}

function errorText(e) {
  const d = e?.response?.data
  if (!d) return e?.message || 'Запустить не удалось'
  if (typeof d === 'string') return d
  if (d.detail) return d.detail
  return Object.entries(d).map(([k, v]) => `${k}: ${[].concat(v).join(', ')}`).join(' · ')
}

function chip(status, text) {
  const [bg, color] = CHIP[status] || ['#F1F5F9', '#475569']
  return <span style={{
    padding: '2px 10px', borderRadius: 100, fontSize: 11, fontWeight: 700, background: bg, color,
  }}>{text}</span>
}

function money(run) {
  // Пустая ставка — не «ноль»: выдуманный тариф хуже отсутствующего.
  // Число — доллары (ставка API приходит в $ за миллион токенов), знак не рисуем.
  if (run.money === null || run.money === undefined) return 'деньги не считаны: ставка не задана'
  return `потрачено ${run.money}`
}

export default function BookIngestPage() {
  const [subjects, setSubjects] = useState([])
  const [file, setFile] = useState(null)
  const [subject, setSubject] = useState('')
  const [language, setLanguage] = useState('ru')
  const [book, setBook] = useState('')
  const [runs, setRuns] = useState([])
  const [open, setOpen] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')

  useEffect(() => { subjectsAPI.list().then(r => setSubjects(r.data)).catch(() => {}) }, [])

  useEffect(() => { ingestAPI.list().then(r => setRuns(r.data)).catch(e => setErr(errorText(e))) }, [])

  // Прогон идёт минутами, поэтому список сам обновляется, пока хоть один «в работе»
  const live = runs.some(r => r.status === 'pending' || r.status === 'running')
  useEffect(() => {
    if (!live) return undefined
    const t = setInterval(() => {
      ingestAPI.list().then(r => setRuns(r.data)).catch(() => {})
    }, 5000)
    return () => clearInterval(t)
  }, [live])

  async function start(e) {
    e.preventDefault()
    setErr(''); setNote(''); setBusy(true)
    try {
      const fd = new FormData()
      fd.append('pdf', file)
      fd.append('subject', subject)
      fd.append('language', language)
      fd.append('book', book)
      const r = await ingestAPI.start(fd)
      setNote(`${r.data.name}: прогон пошёл, страницы и деньги появятся здесь же`)
      setFile(null); setBook('')
      setRuns(prev => [r.data, ...prev])
    } catch (e2) {
      setErr(errorText(e2))
    } finally {
      setBusy(false)
    }
  }

  async function showLog(id) {
    if (open === id) return setOpen(null)
    try {
      const r = await ingestAPI.detail(id)
      setRuns(prev => prev.map(x => (x.id === r.data.id ? r.data : x)))
      setOpen(id)
    } catch (e2) { setErr(errorText(e2)) }
  }

  const ready = file && subject && book.trim()

  return (
    <div style={{ padding: 20, maxWidth: 900 }}>
      <h1 style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 22, margin: '0 0 6px' }}>
        <ScanText size={22} /> Оцифровка книги
      </h1>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 18px' }}>
        Загрузи PDF скана — сервер распознает страницы, разберёт их на задачи и положит
        в <Link to="/teacher/book-bank">банк из книг</Link> черновиками. Приёмку «проверено»
        прогон не ставит: её ставишь только ты. Прогон платной, одна страница — один вызов модели.
      </p>

      <form onSubmit={start} style={card}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <div style={label}>PDF скана</div>
            <input type="file" accept="application/pdf" onChange={e => setFile(e.target.files[0] || null)}
                   style={{ ...field, height: 'auto', padding: '8px 12px', borderStyle: 'dashed' }} />
            {file && <div style={{ fontSize: 12, marginTop: 4 }}>
              {file.name} · {(file.size / 1024 / 1024).toFixed(1)} МБ
            </div>}
          </div>
          <div>
            <div style={label}>Предмет</div>
            <select value={subject} onChange={e => setSubject(e.target.value)} style={field}>
              <option value="">выбери предмет</option>
              {subjects.map(s => <option key={s.slug} value={s.slug}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <div style={label}>Язык задач</div>
            <select value={language} onChange={e => setLanguage(e.target.value)} style={field}>
              {LANGUAGES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
            </select>
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <div style={label}>Метка книги — по ней тема строки отличится от темы другой книги</div>
            <input value={book} onChange={e => setBook(e.target.value)} style={field}
                   placeholder="Касаткина. Электромагнетизм" maxLength={120} />
          </div>
        </div>
        {err && <div style={{ marginTop: 12, color: '#B91C1C', fontSize: 13 }}>{err}</div>}
        {note && <div style={{ marginTop: 12, color: '#15803D', fontSize: 13 }}>{note}</div>}
        <button type="submit" disabled={!ready || busy}
                style={{
                  marginTop: 14, display: 'flex', alignItems: 'center', gap: 8, cursor: ready && !busy ? 'pointer' : 'not-allowed',
                  background: 'var(--primary)', color: '#fff', border: 0, borderRadius: 10, padding: '10px 16px',
                  fontSize: 14, fontWeight: 600, opacity: ready && !busy ? 1 : 0.5,
                }}>
          <Play size={16} /> {busy ? 'запускаю…' : 'Оцифровать книгу'}
        </button>
      </form>

      {runs.length === 0 && <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Прогонов ещё нет.</div>}
      {runs.map(r => (
        <div key={r.id} style={card}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <b style={{ fontSize: 14 }}>{r.book}</b>
            {chip(r.status, r.status === 'running' && r.step ? `${r.status_display}: ${r.step}` : r.status_display)}
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              {r.subject_name} · {r.language} · {r.created_by || '—'}
            </span>
          </div>
          <div style={{ fontSize: 13, marginTop: 8 }}>
            {r.name} · страниц {r.pages} · единиц {r.units} · {money(r)}
            {r.status === 'done' && <span> · <Link to="/teacher/book-bank">открыть в банке</Link></span>}
          </div>
          {r.report && <div style={{ fontSize: 12, marginTop: 6, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
            {r.report}
          </div>}
          {r.error && <div style={{ marginTop: 8, fontSize: 13, color: '#B91C1C', display: 'flex', gap: 6 }}>
            <AlertTriangle size={15} /> {r.error}
          </div>}
          <button onClick={() => showLog(r.id)} type="button"
                  style={{ ...field, marginTop: 10, width: 'auto', cursor: 'pointer', display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            <FileText size={14} /> {open === r.id ? 'скрыть журнал' : 'журнал прогона'}
          </button>
          {open === r.id && (
            <pre style={{
              marginTop: 10, fontSize: 11, background: '#0F172A', color: '#E2E8F0', padding: 12,
              borderRadius: 10, maxHeight: 320, overflow: 'auto', whiteSpace: 'pre-wrap',
            }}>{r.log || 'журнала нет — прогон ещё не начал писать'}</pre>
          )}
        </div>
      ))}
    </div>
  )
}
