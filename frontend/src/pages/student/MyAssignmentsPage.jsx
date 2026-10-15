import { useState, useEffect } from 'react'
import { myAssignmentsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import { ClipboardList, ArrowLeft, Inbox } from 'lucide-react'

// Что видит ученик по своей задаче. `pending_review` — это «ещё не проверено», и
// экран обязан называть это словом, а не нулём: ложного нуля ученик не отличит от
// неверного ответа.
const VERDICT = {
  correct: ['Верно', 'rgba(16,185,129,0.12)', '#065F46'],
  partial: ['Неполно', 'rgba(245,158,11,0.14)', '#92400E'],
  incorrect: ['Неверно', 'rgba(239,68,68,0.1)', '#991B1B'],
  pending_review: ['На проверке у преподавателя', 'rgba(107,114,128,0.12)', '#374151'],
}
const LEVELS = { easy: 'лёгкий', medium: 'средний', hard: 'сложный' }

// «3 балла», «21 балл», «12 баллов» — экран ученика читает человек, а не машина
const points = (n) => {
  const t = n % 10, h = n % 100
  return `${n} ${t === 1 && h !== 11 ? 'балл' : [2, 3, 4].includes(t) && ![12, 13, 14].includes(h) ? 'балла' : 'баллов'}`
}

const chip = (bg, color) => ({
  padding: '2px 8px', borderRadius: 100, fontSize: 11, fontWeight: 600, background: bg, color,
})

function errorText(e) {
  const d = e?.response?.data
  if (!d) return e?.message || 'Запрос не прошёл'
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.join(' · ')
  return Object.entries(d).map(([k, v]) => `${k}: ${[].concat(v).join(', ')}`).join(' · ')
}

const fmtDate = (v) => (v ? String(v).slice(0, 16).replace('T', ' ') : '')

function VerdictChip({ verdict }) {
  const [text, bg, color] = VERDICT[verdict] || VERDICT.pending_review
  return <span style={chip(bg, color)}>{text}</span>
}

export default function MyAssignmentsPage() {
  const [items, setItems] = useState([])
  const [lesson, setLesson] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [answers, setAnswers] = useState({})
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(0)
  const [notice, setNotice] = useState('')
  const [sent, setSent] = useState('')

  const open = (id, sentMsg = '') => {
    setLoading(true)
    setNotice('')
    myAssignmentsAPI.detail(id)
      .then(res => {
        setLesson(res.data)
        setSent(sentMsg)
        // черновик поля = то, что уже сохранено: правка прежнего ответа не должна
        // выглядеть как пустая строка
        const saved = {}
        const byQ = {}
        res.data.blocks.forEach(b => b.answers.forEach(a => {
          saved[a.question] = a.raw_answer
          byQ[a.question] = a
        }))
        setDrafts(saved)
        setAnswers(byQ)
      })
      .catch(e => setNotice(errorText(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    myAssignmentsAPI.list().then(res => setItems(res.data)).catch(e => setNotice(errorText(e)))
      .finally(() => setLoading(false))
  }, [])

  const save = (block, q) => {
    const raw = drafts[q.id] || ''
    if (!raw.trim()) return
    setBusy(q.id)
    setNotice('')
    myAssignmentsAPI.answer(lesson.id, { block: block.id, question: q.id, raw_answer: raw })
      .then(res => setAnswers(a => ({ ...a, [q.id]: { ...a[q.id], ...res.data, question: q.id } })))
      .catch(e => setNotice(errorText(e)))
      .finally(() => setBusy(0))
  }

  // сдача блока перепроверяет все сохранённые ответы заново, поэтому после неё
  // берём урок целиком, а не чиним локальные статусы
  const submit = (block) => {
    if (!confirm(`Сдать блок «${block.label}»?`)) return
    setBusy(-1)
    setNotice('')
    myAssignmentsAPI.submit(lesson.id, { block: block.id })
      .then(() => open(lesson.id, `Блок «${block.label}» сдан.`))
      .catch(e => setNotice(errorText(e)))
      .finally(() => setBusy(0))
  }

  if (!lesson) {
    return (
      <div>
        <div className="page-header">
          <h1 className="page-title">
            <ClipboardList size={18} strokeWidth={1.5} style={{ verticalAlign: -3, marginRight: 6 }} />
            Мои назначения
          </h1>
          <p className="page-subtitle">
            Урок состоит из блоков: классная работа, домашка, сложные, упрощённые. Домашку и
            упрощённые проверяет машина сразу, классную работу и сложные зачитывает преподаватель.
          </p>
        </div>
        {notice && <div style={{ marginBottom: 14, fontSize: 13, color: '#991B1B' }}>{notice}</div>}
        {loading ? (
          <div className="text-center py-4"><div className="spinner"></div></div>
        ) : !items.length ? (
          <div className="card" style={{ padding: 30, color: 'var(--text-secondary)', fontSize: 13 }}>
            Назначений пока нет.
          </div>
        ) : items.map(a => (
          <div key={a.id} className="card" style={{ padding: 16, marginBottom: 12, cursor: 'pointer' }}
               onClick={() => open(a.id)}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <b style={{ fontSize: 15 }}>{a.title}</b>
              <span style={chip('rgba(99,102,241,0.08)', 'var(--primary)')}>{a.subject_name}</span>
              {a.expired
                ? <span style={chip('rgba(239,68,68,0.1)', '#991B1B')}>срок вышел</span>
                : a.due_at
                  ? <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>до {fmtDate(a.due_at)}</span>
                  : <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>без срока</span>}
              <Inbox size={16} strokeWidth={1.5} style={{ marginLeft: 'auto', color: 'var(--text-secondary)' }} />
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
              {a.blocks.map(b => (
                <span key={`${a.id}-${b.kind}`}
                      style={chip(b.autocheck ? 'rgba(16,185,129,0.08)' : 'rgba(245,158,11,0.14)',
                                  b.autocheck ? '#065F46' : '#92400E')}>
                  {b.label} · {b.tasks}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <button className="btn btn-sm btn-outline" onClick={() => setLesson(null)}
                style={{ borderRadius: 10, padding: '4px 12px', marginBottom: 8 }}>
          <ArrowLeft size={12} strokeWidth={1.5} style={{ verticalAlign: -1, marginRight: 4 }} />К списку
        </button>
        <h1 className="page-title">{lesson.title}</h1>
        <p className="page-subtitle">
          {lesson.subject_name} · {lesson.due_at ? `срок до ${fmtDate(lesson.due_at)}` : 'без срока'}
          {lesson.expired ? ' · срок сдачи вышел, ответы больше не принимаются' : ''}
        </p>
      </div>
      {notice && <div style={{ marginBottom: 14, fontSize: 13, color: '#991B1B' }}>{notice}</div>}
      {sent && !notice && <div style={{ marginBottom: 14 }}><span style={chip('rgba(16,185,129,0.12)', '#065F46')}>{sent}</span></div>}
      {loading ? (
        <div className="text-center py-4"><div className="spinner"></div></div>
      ) : lesson.blocks.map(b => {
        const p = b.progress
        return (
          <div key={b.id} className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 20 }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex',
                          gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <b style={{ fontSize: 14 }}>{b.label}</b>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {b.tasks} задач · {b.autocheck ? 'проверяет машина' : 'зачитывает преподаватель'}
              </span>
              {p && (
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  · решено {p.checked} из {p.total}
                  {p.percent !== null ? ` · ${p.percent} %` : ''}
                  {p.pending ? ` · на проверке ${p.pending}` : ''}
                </span>
              )}
              <button className="btn btn-sm btn-primary" onClick={() => submit(b)}
                      disabled={lesson.expired || busy === -1}
                      style={{ marginLeft: 'auto', borderRadius: 10, padding: '4px 12px' }}>
                {busy === -1 ? 'Сдаю…' : 'Сдать блок'}
              </button>
            </div>
            {b.questions.map((q, i) => {
              const a = answers[q.id]
              return (
                <div key={q.id} style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6, alignItems: 'center' }}>
                    <b style={{ fontSize: 13 }}>{i + 1}</b>
                    <span style={chip('rgba(99,102,241,0.08)', 'var(--primary)')}>{LEVELS[q.difficulty] || q.difficulty}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{points(q.points)}</span>
                    {a && <VerdictChip verdict={a.verdict} />}
                  </div>
                  <div style={{ fontSize: 14 }}><FormattedText text={q.latex || q.text} markdown /></div>
                  {q.image && (
                    <img src={q.image} alt="" style={{ marginTop: 8, maxWidth: '100%', maxHeight: 260, borderRadius: 8 }} />
                  )}
                  <textarea value={drafts[q.id] || ''} disabled={lesson.expired}
                            onChange={e => setDrafts(d => ({ ...d, [q.id]: e.target.value }))}
                            placeholder="Решение и ответ — как в тетради" rows={3}
                            style={{ width: '100%', marginTop: 10, borderRadius: 10, padding: 10, fontSize: 13,
                                     border: '1px solid var(--border)', fontFamily: 'inherit', resize: 'vertical',
                                     background: lesson.expired ? 'rgba(107,114,128,0.06)' : '#fff' }} />
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
                    <button className="btn btn-sm btn-outline" onClick={() => save(b, q)}
                            disabled={lesson.expired || !(drafts[q.id] || '').trim() || busy === q.id}
                            style={{ borderRadius: 10, padding: '4px 12px' }}>
                      {busy === q.id ? 'Сохраняю…' : 'Сохранить ответ'}
                    </button>
                    {a && a.id && (
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        {(a.feedback || {}).note}
                      </span>
                    )}
                  </div>
                  {a && (a.feedback || {}).etalon && (
                    <div style={{ marginTop: 8, fontSize: 13 }}>
                      <b style={{ fontSize: 11, color: 'var(--text-secondary)' }}>ПРАВИЛЬНЫЙ ОТВЕТ · </b>
                      <FormattedText text={(a.feedback || {}).etalon} markdown />
                    </div>
                  )}
                </div>
              )
            })}
            {!b.questions.length && (
              <div style={{ padding: 20, fontSize: 13, color: 'var(--text-secondary)' }}>В блоке нет задач.</div>
            )}
          </div>
        )
      })}
    </div>
  )
}
