import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { myAssignmentsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import { leaveDemoSession, savedReturnSession } from '../auth/lessonPreview'
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

// Кнопка сдачи живёт и в шапке блока, и под его последней задачей: после десятой
// задачи крутить весь экран обратно наверх ученик не обязан.
function SubmitControls({ big, expired, busy, flushing, asking, onAsk, onCancel, onConfirm }) {
  const disabled = expired || busy === -1 || flushing
  return (
    <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      <button className={big ? 'btn btn-primary' : 'btn btn-sm btn-primary'}
              onClick={onAsk} disabled={disabled || asking}
              style={{ borderRadius: 10, padding: big ? '10px 26px' : '4px 12px',
                       fontSize: big ? 15 : undefined }}>
        {flushing ? 'Сохраняю ответы…' : busy === -1 ? 'Сдаю…' : 'Сдать блок'}
      </button>
      {asking && (
        <>
          <button className="btn btn-sm btn-primary" onClick={onConfirm} disabled={disabled}
                  style={{ borderRadius: 10, padding: '4px 12px' }}>
            Подтвердить сдачу
          </button>
          <button className="btn btn-sm btn-outline" onClick={onCancel}
                  style={{ borderRadius: 10, padding: '4px 12px' }}>
            Отмена
          </button>
        </>
      )}
    </span>
  )
}

// Экран открыт дежурным учеником (предпросмотр урока тренером): своя сессия лежит в
// `localStorage` под отдельным ключом, и одной кнопкой человек возвращается назад —
// иначе «посмотреть глазами ученика» означало бы потерять свой вход.
function DemoBanner() {
  if (!savedReturnSession()) return null
  return (
    <div style={{ marginBottom: 14, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap',
                  border: '1px solid rgba(245,158,11,0.35)', background: 'rgba(245,158,11,0.08)',
                  borderRadius: 10, padding: '8px 12px', fontSize: 12, color: '#92400E' }}>
      Это тестовый вход: урок открыт дежурным учеником, его ответы попадут в отдельную строку матрицы.
      <button className="btn btn-sm btn-outline" style={{ borderRadius: 10, padding: '4px 12px' }}
              onClick={() => {
                const back = leaveDemoSession()
                if (back) window.location.replace(back)
              }}>
        Выйти из тестового входа
      </button>
    </div>
  )
}

export default function MyAssignmentsPage() {
  const [items, setItems] = useState([])
  const [lesson, setLesson] = useState(null)
  const [drafts, setDrafts] = useState({})
  // что реально лежит на сервере: по этому свершению поле считается «изменённым»,
  // поэтому потеря связи с кнопкой «Сохранить ответ» не означает потерю ответа
  const [baseline, setBaseline] = useState({})
  const [ticks, setTicks] = useState({})
  const [answers, setAnswers] = useState({})
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(0)
  const [flushing, setFlushing] = useState(false)
  // сдача необратима для ученика только ощущением, поэтому подтверждение живёт тут же,
  // а не в системном окне: нативный `confirm()` и человеку мешает, и автотест вешает
  const [askBlock, setAskBlock] = useState(0)
  const [notice, setNotice] = useState('')
  const [sent, setSent] = useState('')
  const [params] = useSearchParams()

  const open = (id, sentMsg = '') => {
    setLoading(true)
    setNotice('')
    setAskBlock(0)
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
        setBaseline(saved)
        setTicks({})
        setAnswers(byQ)
      })
      .catch(e => setNotice(errorText(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    myAssignmentsAPI.list().then(res => setItems(res.data)).catch(e => setNotice(errorText(e)))
      .finally(() => setLoading(false))
  }, [])

  // вход из урока GetCourse приходит как `/assignments?open=<id>`: ученик обязан
  // попасть сразу в карточку урока, а не остановиться на списке
  useEffect(() => {
    const id = Number(params.get('open'))
    if (id) open(id)
  }, [])

  // Черновик считается изменённым, только если он непустой и отличается от того,
  // что уже легло на сервер: пустое поле сдавать нечем, а неизменённое — не о чем
  // просить сервер дважды.
  const dirtyFor = (id) => {
    const raw = drafts[id] || ''
    return raw.trim() !== '' && raw !== (baseline[id] || '')
  }

  // `silent` — путь onBlur и сдачи: сохранение идёт тихо, без кнопки «Сохраняю…»,
  // а ученик видит только «Сохранено ✓»
  const save = (block, q, silent) => {
    const raw = drafts[q.id] || ''
    if (raw.trim() === '' || raw === (baseline[q.id] || '')) return Promise.resolve(false)
    if (!silent) setBusy(q.id)
    setNotice('')
    return myAssignmentsAPI.answer(lesson.id, { block: block.id, question: q.id, raw_answer: raw })
      .then(res => {
        setAnswers(prev => ({ ...prev, [q.id]: { ...prev[q.id], ...res.data, question: q.id } }))
        setBaseline(prev => ({ ...prev, [q.id]: raw }))
        setTicks(prev => ({ ...prev, [q.id]: true }))
        return true
      })
      .catch(e => { setNotice(errorText(e)); return false })
      .finally(() => { if (!silent) setBusy(0) })
  }

  // Сдача не имеет права терять введённое: сначала досохраняем каждое поле, которого
  // сервер ещё не видел, и только на ответ сервера идём в `submit`.
  const flushAndSubmit = (block) => {
    setAskBlock(0)
    setFlushing(true)
    setNotice('')
    const pending = block.questions.filter(q => dirtyFor(q.id)).map(q => save(block, q, true))
    Promise.all(pending)
      .then(results => {
        setFlushing(false)
        if (results.some(ok => ok === false)) return
        setBusy(-1)
        // сдача блока перепроверяет все сохранённые ответы заново, поэтому после неё
        // берём урок целиком, а не чиним локальные статусы
        return myAssignmentsAPI.submit(lesson.id, { block: block.id })
          .then(() => open(lesson.id, `Блок «${block.label}» сдан.`))
          .catch(e => setNotice(errorText(e)))
      })
      .finally(() => { setFlushing(false); setBusy(0) })
  }

  if (!lesson) {
    return (
      <div>
        <DemoBanner />
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
      <DemoBanner />
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
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
                <SubmitControls expired={lesson.expired} busy={busy} flushing={flushing}
                                asking={askBlock === b.id} onAsk={() => setAskBlock(b.id)}
                                onCancel={() => setAskBlock(0)} onConfirm={() => flushAndSubmit(b)} />
              </span>
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
                            onBlur={() => { if (dirtyFor(q.id)) save(b, q, true) }}
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
                    {ticks[q.id] && !dirtyFor(q.id) && (
                      <span style={chip('rgba(16,185,129,0.12)', '#065F46')}>Сохранено ✓</span>
                    )}
                    {dirtyFor(q.id) && (
                      <span style={{ fontSize: 12, color: '#92400E' }}>Не сохранено — сохранится само при сдаче</span>
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
            {b.questions.length > 0 && (
              <div style={{ padding: '18px 20px', textAlign: 'center' }}>
                <SubmitControls big expired={lesson.expired} busy={busy} flushing={flushing}
                                asking={askBlock === b.id} onAsk={() => setAskBlock(b.id)}
                                onCancel={() => setAskBlock(0)} onConfirm={() => flushAndSubmit(b)} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
