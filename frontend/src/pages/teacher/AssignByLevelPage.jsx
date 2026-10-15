import { useState, useEffect } from 'react'
import { assignmentsAPI, subjectsAPI, groupsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import { ClipboardList, RefreshCw, AlertTriangle, ChevronDown, ChevronRight, Undo2,
         Send, Check, X, Link2 } from 'lucide-react'

// Четыре блока — это схема урока, а не набор подписей на выбор: что сверяет машина,
// решает бэкенд (`homework`/`simplified`), и экран обязан говорить это прямо,
// иначе тренер посчитает «классную работу» непроверенной домашкой.
const KINDS = [
  ['in_class', 'Классная работа', 'решают вместе на уроке — машина не сверяет'],
  ['homework', 'Домашка', 'открытый ответ сверяет машина'],
  ['advanced', 'Сложные', 'запас для сильных — машина не сверяет'],
  ['simplified', 'Упрощённые', 'база, которую сверяет машина'],
]
const KIND_NAME = Object.fromEntries(KINDS.map(([k, n]) => [k, n]))
const LEVELS = [['easy', 'Лёгкий'], ['medium', 'Средний'], ['hard', 'Сложный']]
const levelName = (v) => (LEVELS.find(([k]) => k === v) || [, v])[1]
// ступень по умолчанию повторяет смысл блока: «Сложные» — это hard, «Упрощённые» — easy,
// и тренеру не нужно каждый раз угадывать переключатель
const DEFAULT_LEVEL = { in_class: 'medium', homework: 'medium', advanced: 'hard', simplified: 'easy' }
const SOURCES = [['', 'Любой источник'], ['book_scan', 'Только оцифрованные из книг'],
                 ['collected', 'Только собранные'], ['authorial', 'Только авторские']]
const GRADES = ['', '5', '6', '7', '8', '9', '10', '11']

const chip = (bg, color) => ({
  padding: '2px 8px', borderRadius: 100, fontSize: 11, fontWeight: 600, background: bg, color,
})
const sel = {
  height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px',
  fontSize: 13, background: '#fff', cursor: 'pointer', maxWidth: 300,
}
const label = { fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }

function errorText(e) {
  const d = e?.response?.data
  if (!d) return e?.message || 'Запрос не прошёл'
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.join(' · ')
  return Object.entries(d).map(([k, v]) => `${k}: ${[].concat(v).join(', ')}`).join(' · ')
}

const blankBlocks = () => Object.fromEntries(KINDS.map(([k]) => [
  k, { level: DEFAULT_LEVEL[k], count: 10, nonce: 0, rows: [], checked: [], pool: null, sizes: null, sig: '', touched: false },
]))

// Строка набора: тот же рендер, что в банке, плюс номер, страница и класс из паспорта —
// по ним тренер находит задачу в книге, если ученик спросит про неё. Бейдж «Без
// автопроверки» стоит на задаче без напечатанного ответа: сверять нечего, вердикт по
// ней всё равно ставит человек. `picked === null` — строка без галочки, так выглядит
// состав уже собранного урока.
function TaskRow({ q, picked, onToggle, showAnswer }) {
  const pr = q.provenance || {}
  const noEtalon = !(q.latex_answer || '').trim()
  return (
    <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 12 }}>
      {picked !== null && (
        <input type="checkbox" checked={picked} title="Включить задачу в блок"
               onChange={e => onToggle(e.target.checked)}
               style={{ width: 16, height: 16, accentColor: 'var(--primary)', cursor: 'pointer', marginTop: 3 }} />
      )}
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
          {pr.num && <span style={chip('rgba(37,99,235,0.1)', '#1E40AF')}>№ {pr.num}</span>}
          <span style={chip('rgba(16,185,129,0.08)', '#065F46')}>{q.topic_name}</span>
          <span style={chip('rgba(99,102,241,0.08)', 'var(--primary)')}>{levelName(q.difficulty)}</span>
          {q.grade ? <span style={chip('rgba(107,114,128,0.12)', '#374151')}>класс {q.grade}</span> : null}
          {noEtalon && <span style={chip('rgba(245,158,11,0.14)', '#92400E')}>Без автопроверки (ручной зачёт)</span>}
          {(q.uncertain || []).length > 0 && (
            <span style={chip('rgba(239,68,68,0.1)', '#991B1B')}>
              <AlertTriangle size={11} strokeWidth={1.5} style={{ verticalAlign: -1 }} /> спорных знаков: {q.uncertain.length}
            </span>
          )}
          {pr.page && <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{pr.book || pr.run} · с. {pr.page}</span>}
        </div>
        <div style={{ fontSize: 14 }}><FormattedText text={q.latex || q.text} markdown /></div>
        {q.image && (
          <img src={q.image} alt="" style={{ marginTop: 8, maxWidth: '100%', maxHeight: 220, borderRadius: 8 }} />
        )}
        {showAnswer && (
          <div style={{ marginTop: 8, fontSize: 13 }}>
            <b style={{ fontSize: 11, color: 'var(--text-secondary)' }}>ОТВЕТ В БАНКЕ · </b>
            {noEtalon ? <span style={{ color: '#92400E' }}>не напечатан — проверяет преподаватель</span>
                      : <FormattedText text={q.latex_answer} markdown />}
          </div>
        )}
      </div>
    </div>
  )
}

// Матрица результатов одного урока: строки — ученики, колонки — блоки, и под ней
// очередь `pending_review` с быстрым вердиктом. Эталон книги показан только здесь:
// ни на один экран ученика он не уходит.
function LessonResults({ assignment }) {
  const [mx, setMx] = useState(null)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(0)

  const load = () => assignmentsAPI.matrix(assignment.id)
    .then(res => { setMx(res.data); setNotice('') })
    .catch(e => setNotice(errorText(e)))

  useEffect(() => { load() }, [assignment.id])

  const judge = (answer, verdict) => {
    setBusy(answer.id)
    setNotice('')
    assignmentsAPI.review(answer.id, { verdict }).then(load).catch(e => setNotice(errorText(e)))
      .finally(() => setBusy(0))
  }

  if (!mx) {
    return <div style={{ padding: 20 }}>{notice
      ? <div style={{ fontSize: 13, color: '#991B1B' }}>{notice}</div>
      : <div className="spinner"></div>}</div>
  }

  const state = { in_progress: 'решает', submitted: 'сдал', reviewed: 'проверено' }
  return (
    <div style={{ padding: '4px 20px 18px', background: 'rgba(99,102,241,0.03)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, marginTop: 12 }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--text-secondary)' }}>
            <th style={{ padding: '6px 8px', fontWeight: 600 }}>Ученик</th>
            {mx.blocks.map(b => (
              <th key={b.id} style={{ padding: '6px 8px', fontWeight: 600 }}>
                {b.label}{!b.autocheck && <span style={{ color: '#92400E' }}> · вручную</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {mx.rows.map(row => (
            <tr key={row.student} style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ padding: '6px 8px', fontWeight: 600 }}>{row.name}</td>
              {row.blocks.map(cell => (
                <td key={cell.block} style={{ padding: '6px 8px' }}>
                  {!cell.state && <span style={{ color: 'var(--text-secondary)' }}>— не сдавал</span>}
                  {!!cell.state && (
                    <span title={state[cell.state] || cell.state}>
                      {cell.percent === null ? '—' : `${cell.percent} %`}
                      <span style={{ color: 'var(--text-secondary)' }}> {cell.checked}/{cell.total}</span>
                      {cell.pending > 0 && (
                        <span style={chip('rgba(245,158,11,0.14)', '#92400E')}>на проверке {cell.pending}</span>
                      )}
                    </span>
                  )}
                </td>
              ))}
            </tr>
          ))}
          {!mx.rows.length && (
            <tr>
              <td colSpan={mx.blocks.length + 1} style={{ padding: 12, color: 'var(--text-secondary)' }}>
                У урока нет учеников — сдавать некому.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div style={{ marginTop: 16, fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>
        Ждут вердикта · {mx.pending_review.length}
      </div>
      {notice && <div style={{ margin: '8px 0', fontSize: 13, color: '#991B1B' }}>{notice}</div>}
      {!mx.pending_review.length && (
        <div style={{ padding: '10px 0 4px', fontSize: 13, color: 'var(--text-secondary)' }}>
          Непроверенных ответов нет.
        </div>
      )}
      {mx.pending_review.map(a => (
        <div key={a.id} style={{ borderTop: '1px solid var(--border)', padding: '12px 0' }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
            <b style={{ fontSize: 13 }}>{a.student_name}</b>
            <span style={chip('rgba(99,102,241,0.08)', 'var(--primary)')}>{KIND_NAME[a.block_kind]}</span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{a.verdict_note}</span>
          </div>
          <div style={{ fontSize: 13 }}><FormattedText text={a.question_text} markdown /></div>
          <div style={{ fontSize: 13, marginTop: 6 }}>
            <b style={{ fontSize: 11, color: 'var(--text-secondary)' }}>ОТВЕТ УЧЕНИКА · </b>{a.raw_answer || '—'}
          </div>
          {a.normalized_answer && (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>вычленила машина: {a.normalized_answer}</div>
          )}
          <div style={{ fontSize: 13, marginTop: 4 }}>
            <b style={{ fontSize: 11, color: 'var(--text-secondary)' }}>ЭТАЛОН ИЗ БАНКА · </b>
            {a.etalon ? <FormattedText text={a.etalon} markdown />
                       : <span style={{ color: '#92400E' }}>в книге ответа нет</span>}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button className="btn btn-sm btn-primary" onClick={() => judge(a, 'correct')}
                    disabled={busy === a.id} style={{ borderRadius: 10, padding: '4px 12px' }}>
              <Check size={12} strokeWidth={2} style={{ verticalAlign: -1, marginRight: 4 }} />Зачесть
            </button>
            <button className="btn btn-sm btn-outline" onClick={() => judge(a, 'incorrect')}
                    disabled={busy === a.id}
                    style={{ borderRadius: 10, padding: '4px 12px', color: '#991B1B' }}>
              <X size={12} strokeWidth={2} style={{ verticalAlign: -1, marginRight: 4 }} />Отклонить
            </button>
            <button className="btn btn-sm btn-outline" onClick={() => judge(a, 'partial')}
                    disabled={busy === a.id} style={{ borderRadius: 10, padding: '4px 12px' }}>
              Половина балла
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

// GetCourse подставляет макросы в URL урока сам, но HMAC-подпись посчитать не может:
// шаблон уезжает в урок с `{ts}` и `{sign}` заглушками, живые значения выдаёт платформа.
// Пока `GC_SSO_SECRET` не задан, переход по такой ссылке отклоняется — это не дырка,
// а ожидание его решения, как считать подпись на каждого ученика.
function GcLinkButton({ assignment }) {
  const [copied, setCopied] = useState('')
  const link = `${window.location.origin}/api/lesson/join/` +
    `?gc_uid={uid}&email={email}&first_name={first_name}&last_name={last_name}` +
    `&assignment_id=${assignment.id}&ts={ts}&sign={sign}`
  const note = 'Макросы {uid} и {email} подставит GetCourse. {ts} и {sign} считает ' +
               'платформа на каждого ученика: без живой подписи вход отклоняется.'
  // буфер обмена отказывает (http, фокус) — шаблон всё равно показываем, чтобы
  // методист не остался с пустым кликом
  const copy = () => navigator.clipboard?.writeText(link).then(() => setCopied('ok'),
                                                               () => setCopied('manual'))
  return (
    <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 6 }}>
      <button className="btn btn-sm btn-outline" onClick={copy}
              style={{ borderRadius: 10, padding: '4px 12px' }}>
        <Link2 size={12} strokeWidth={1.5} style={{ verticalAlign: -1, marginRight: 4 }} />
        {copied === 'ok' ? 'Скопировано' : copied === 'manual' ? 'Скопируй вручную'
                        : 'Ссылка для GetCourse'}
      </button>
      {copied && (
        <span style={{ fontSize: 11, color: 'var(--text-secondary)', maxWidth: 520,
                       background: 'rgba(99,102,241,0.06)', borderRadius: 8, padding: '6px 8px' }}>
          <span style={{ fontFamily: 'ui-monospace, monospace', wordBreak: 'break-all' }}>{link}</span>
          <span style={{ display: 'block', marginTop: 4 }}>{note}</span>
        </span>
      )}
    </span>
  )
}

export default function AssignByLevelPage() {
  const [subjects, setSubjects] = useState([])
  const [subject, setSubject] = useState('')
  const [topics, setTopics] = useState([])
  const [topic, setTopic] = useState('')
  const [grade, setGrade] = useState('')
  const [source, setSource] = useState('')
  const [kind, setKind] = useState('homework')
  const [bl, setBl] = useState(blankBlocks)
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState('')

  const [groups, setGroups] = useState([])
  const [group, setGroup] = useState('')
  const [needle, setNeedle] = useState('')
  const [students, setStudents] = useState([])
  const [to, setTo] = useState([])
  const [title, setTitle] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [mine, setMine] = useState([])
  const [open, setOpen] = useState(null)
  const [results, setResults] = useState(null)
  const [busy, setBusy] = useState(false)

  const active = bl[kind]
  const patchActive = (patch) => setBl(b => ({ ...b, [kind]: { ...b[kind], ...patch } }))
  // Галочка тренера — ручная сборка блока: с неё экран перестаёт трогать состав при
  // смене фильтра, иначе фильтр «Класс» съедал бы уже набранные задачи.
  const setActive = (checked) => patchActive({ checked, touched: true })

  const load = (k, level, count) => {
    if (!subject) return
    // Переход на вкладку блока — не смена фильтра. Набор этого блока уже загружен,
    // и в нём лежит ручной отбор тренера: перегруз по той же сигнатуре поставил бы
    // галочки на весь список заново и тихо выбросил собранные задачи.
    const sig = [subject, level, count, topic, source, grade, bl[k].nonce].join('|')
    if (bl[k].sig === sig) return
    setLoading(true)
    setNotice('')
    const params = { subject, kind: k, difficulty: level, count }
    if (topic) params.topic = topic
    if (source) params.source_type = source
    if (grade) params.grade = grade
    assignmentsAPI.pick(params)
      // Пока блок не тронут руками, набор блока = то, что экран показал. После первой
      // галочки состав принадлежит тренеру: новый фильтр только показывает другие задачи.
      .then(res => setBl(b => ({
        ...b,
        [k]: { ...b[k], rows: res.data.questions,
               checked: b[k].touched ? b[k].checked : res.data.questions.map(q => q.id),
               pool: res.data.pool, sizes: res.data.levels, sig },
      })))
      .catch(e => {
        setBl(b => ({ ...b, [k]: { ...b[k], rows: [], checked: [], pool: null, sizes: null, sig: '' } }))
        setNotice(errorText(e))
      })
      .finally(() => setLoading(false))
  }

  // ступень и число правят вводом: без паузы каждый символ — запрос к банку
  useEffect(() => {
    if (!subject) return
    const t = setTimeout(() => load(kind, active.level, active.count), 350)
    return () => clearTimeout(t)
  }, [subject, topic, grade, source, kind, active.level, active.count, active.nonce])

  useEffect(() => {
    subjectsAPI.list().then(res => setSubjects(res.data)).catch(() => {})
    groupsAPI.list().then(res => setGroups(res.data)).catch(() => {})
    assignmentsAPI.list().then(res => setMine(res.data)).catch(() => {})
  }, [])

  useEffect(() => {
    if (subject) subjectsAPI.topics(subject).then(res => setTopics(res.data)).catch(() => setTopics([]))
    else setTopics([])
    setTopic('')
  }, [subject])

  useEffect(() => {
    const t = setTimeout(() => {
      groupsAPI.searchStudents(needle.trim(), group)
        .then(res => setStudents(res.data)).catch(() => setStudents([]))
    }, 350)
    return () => clearTimeout(t)
  }, [needle, group])

  const totalChosen = KINDS.reduce((n, [k]) => n + bl[k].checked.length, 0)
  const subjectName = (subjects.find(s => s.id === Number(subject)) || {}).name || ''

  const create = () => {
    const blocks = KINDS.map(([k]) => ({ kind: k, question_ids: bl[k].checked }))
      .filter(b => b.question_ids.length)
    if (!blocks.length || !(to.length || group)) return
    const whom = to.length
      ? `${to.length} уч.`
      : `группе «${(groups.find(g => g.id === Number(group)) || {}).name}»`
    if (!confirm(`Собрать урок: ${blocks.length} блока, ${totalChosen} задач — ${whom}? Ученики увидят его после публикации.`)) return
    setBusy(true)
    setNotice('')
    assignmentsAPI.create({
      title: title.trim() || subjectName,
      subject: Number(subject),
      students: to,
      ...(dueAt ? { due_at: dueAt } : {}),
      blocks,
    })
      // create отвечает записным сериализатором, в нём нет ни задач, ни названий
      // блоков, поэтому в список берём полный слепок урока
      .then(res => assignmentsAPI.detail(res.data.id))
      .then(res => {
        setMine(ms => [res.data, ...ms])
        setTitle('')
        setDueAt('')
        setBl(blankBlocks())
        setTick(t => t + 1)
      })
      .catch(e => setNotice(errorText(e)))
      .finally(() => setBusy(false))
  }

  const publish = (a) => {
    if (!confirm(`Опубликовать «${a.title}»? ${a.students.length} уч. увидят его сразу.`)) return
    setNotice('')
    assignmentsAPI.publish(a.id)
      .then(res => setMine(ms => ms.map(m => (m.id === res.data.id ? res.data : m))))
      .catch(e => setNotice(errorText(e)))
  }

  const revoke = (a) => {
    if (!confirm(`Отозвать «${a.title}»? Ученики перестанут его видеть, запись останется.`)) return
    setNotice('')
    assignmentsAPI.revoke(a.id)
      .then(res => setMine(ms => ms.map(m => (m.id === res.data.id ? res.data : m))))
      .catch(e => setNotice(errorText(e)))
  }

  // Список уроков отдаёт блоки без задач — состав берёт из detail по стрелке, иначе
  // тренер видел бы пустой блок там, где десять назначенных задач.
  const showTasks = (id) => {
    if (open && open.id === id) { setOpen(null); return }
    assignmentsAPI.detail(id).then(res => setOpen(res.data)).catch(e => setNotice(errorText(e)))
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          <ClipboardList size={18} strokeWidth={1.5} style={{ verticalAlign: -3, marginRight: 6 }} />
          Конструктор урока
        </h1>
        <p className="page-subtitle">
          Урок собирается из четырёх блоков: классная работа, домашка, сложные, упрощённые.
          Сверяет машина только домашку и упрощённые — классную работу и сложные зачитывает человек.
          Состав блока фиксируется в момент создания урока, поэтому следующий перегон книги его не изменит.
          Черновик в набор не попадает: ученику уходит только принятая задача.
        </p>
      </div>

      <div className="card" style={{ padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div>
            <div style={label}>Предмет</div>
            <select value={subject} onChange={e => setSubject(e.target.value)} style={sel}>
              <option value="">— выбрать —</option>
              {subjects.map(s => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
            </select>
          </div>
          <div>
            <div style={label}>Класс</div>
            <select value={grade} onChange={e => setGrade(e.target.value)} style={{ ...sel, width: 130 }}
                    title="Печатный уровень книги, 5–11. «Любой» оставляет в наборе и задачи без разметки класса">
              {GRADES.map(g => <option key={g} value={g}>{g ? `класс ${g}` : 'любой'}</option>)}
            </select>
          </div>
          <div>
            <div style={label}>Тема</div>
            <select value={topic} onChange={e => setTopic(e.target.value)} disabled={!subject} style={sel}>
              <option value="">Все темы</option>
              {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <div>
            <div style={label}>Источник</div>
            <select value={source} onChange={e => setSource(e.target.value)} style={sel}>
              {SOURCES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
            </select>
          </div>
        </div>
        {notice && <div style={{ marginTop: 10, fontSize: 13, color: '#991B1B' }}>{notice}</div>}
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: 12,
                      borderBottom: '1px solid var(--border)' }}>
          {KINDS.map(([k, n, note]) => (
            <button key={k} className={`btn btn-sm ${kind === k ? 'btn-primary' : 'btn-outline'}`}
                    onClick={() => setKind(k)} disabled={!subject}
                    title={note} style={{ borderRadius: 10, padding: '6px 12px' }}>
              {n} · {bl[k].checked.length}
            </button>
          ))}
        </div>

        <div style={{ padding: 12, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end',
                      borderBottom: '1px solid var(--border)' }}>
          <div>
            <div style={label}>Ступень блока</div>
            <div style={{ display: 'flex', gap: 6 }}>
              {LEVELS.map(([v, n]) => (
                <button key={v} className={`btn btn-sm ${active.level === v ? 'btn-primary' : 'btn-outline'}`}
                        onClick={() => patchActive({ level: v })}
                        disabled={!subject || (active.sizes && !active.sizes[v])}
                        title={active.sizes ? `в банке этого уровня: ${active.sizes[v]}` : 'сначала предмет'}
                        style={{ borderRadius: 10, padding: '6px 12px' }}>
                  {n}{active.sizes ? ` · ${active.sizes[v]}` : ''}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div style={label}>Сколько задач</div>
            <input type="number" min="1" max="50" value={active.count} style={{ ...sel, width: 90 }}
                   onChange={e => patchActive({ count: Math.max(1, Math.min(50, Number(e.target.value) || 1)) })} />
          </div>
          <button className="btn btn-sm btn-outline" disabled={!subject}
                  onClick={() => patchActive({ nonce: active.nonce + 1 })}
                  title="Другой случайный набор того же фильтра"
                  style={{ borderRadius: 10, padding: '6px 12px', marginBottom: 1 }}>
            <RefreshCw size={12} strokeWidth={1.5} style={{ verticalAlign: -1, marginRight: 4 }} />Перемешать
          </button>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', marginLeft: 'auto', paddingBottom: 6 }}>
            {KINDS.find(([k]) => k === kind)[2]}
          </span>
        </div>

        <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)', fontSize: 13,
                      fontWeight: 600, color: 'var(--text-secondary)', display: 'flex', gap: 10, alignItems: 'center' }}>
          {subject
            ? `${KIND_NAME[kind]} · задач под фильтр ${active.pool === null ? '…' : active.pool} · показано ${active.rows.length} · в блоке ${active.checked.length}`
            : 'Набор пока пуст: выберите предмет'}
          {active.rows.length > 0 && (
            <button className="btn btn-sm btn-outline" style={{ marginLeft: 'auto', borderRadius: 10, padding: '4px 12px' }}
                    onClick={() => setActive(active.checked.length === active.rows.length
                      ? [] : active.rows.map(r => r.id))}>
              {active.checked.length === active.rows.length ? 'Снять все' : 'Выбрать все'}
            </button>
          )}
        </div>
        {loading ? (
          <div className="text-center py-4"><div className="spinner"></div></div>
        ) : active.rows.length === 0 ? (
          <div style={{ padding: 30, color: 'var(--text-secondary)', fontSize: 13 }}>
            Под этот блок и фильтр принятых задач нет. Смените ступень, класс, источник или число задач.
          </div>
        ) : active.rows.map(q => (
          <TaskRow key={q.id} q={q} picked={active.checked.includes(q.id)} showAnswer
                   onToggle={on => setActive(on ? [...active.checked, q.id]
                                                 : active.checked.filter(i => i !== q.id))} />
        ))}
      </div>

      <div className="card" style={{ padding: 16, marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
          Состав урока · {totalChosen} задач
        </div>
        {KINDS.map(([k, n]) => (
          <div key={k} style={{ fontSize: 13, padding: '3px 0', display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ minWidth: 150 }}>{n}</span>
            <span style={{ color: 'var(--text-secondary)' }}>
              {bl[k].checked.length ? `${bl[k].checked.length} задач` : 'пусто'}
            </span>
            {bl[k].checked.length > 0 && k !== kind && (
              <button className="btn btn-sm btn-outline" onClick={() => setKind(k)}
                      style={{ borderRadius: 8, padding: '1px 8px', fontSize: 11 }}>править</button>
            )}
          </div>
        ))}
      </div>

      <div className="card" style={{ padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div>
            <div style={label}>Группа</div>
            <select value={group} onChange={e => setGroup(e.target.value)} style={sel}>
              <option value="">Все ученики</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          <div>
            <div style={label}>Поиск ученика</div>
            <input value={needle} onChange={e => setNeedle(e.target.value)} placeholder="фамилия или логин"
                   style={{ ...sel, width: 240, cursor: 'text' }} />
          </div>
          <div style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-secondary)' }}>
            выбрано учеников: {to.length}
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', marginTop: 12,
                      maxHeight: 180, overflowY: 'auto' }}>
          {students.map(s => (
            <label key={s.id} style={{ fontSize: 13, display: 'inline-flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
              <input type="checkbox" checked={to.includes(s.id)} style={{ accentColor: 'var(--primary)' }}
                     onChange={e => setTo(rs => e.target.checked ? [...rs, s.id] : rs.filter(i => i !== s.id))} />
              {s.full_name || s.username}
            </label>
          ))}
          {!students.length && <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Учеников под фильтр поиска нет.</span>}
        </div>
      </div>

      <div className="card" style={{ padding: 16, marginBottom: 20, display: 'flex', gap: 10,
                                     alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div style={{ minWidth: 240, flexGrow: 1 }}>
          <div style={label}>Название урока</div>
          <input value={title} onChange={e => setTitle(e.target.value)}
                 style={{ ...sel, width: '100%', cursor: 'text' }} placeholder={subjectName} />
        </div>
        <div>
          <div style={label}>Срок сдачи</div>
          <input type="datetime-local" value={dueAt} onChange={e => setDueAt(e.target.value)}
                 style={{ ...sel, cursor: 'text', width: 210 }} />
        </div>
        <button className="btn btn-primary" onClick={create}
                disabled={!subject || !totalChosen || !(to.length || group) || busy}
                style={{ marginLeft: 'auto', borderRadius: 10, padding: '8px 16px' }}>
          {busy ? 'Собираю…' : `Создать урок${totalChosen ? ` · ${totalChosen} задач` : ''}`}
        </button>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontSize: 13,
                      fontWeight: 600, color: 'var(--text-secondary)' }}>
          Мои уроки · {mine.length}
        </div>
        {!mine.length && (
          <div style={{ padding: 30, color: 'var(--text-secondary)', fontSize: 13 }}>
            Уроков ещё нет.
          </div>
        )}
        {mine.map(a => {
          const detail = open && open.id === a.id ? open : null
          return (
            <div key={a.id} style={{ borderBottom: '1px solid var(--border)' }}>
              <div style={{ padding: '14px 20px', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <button className="btn btn-sm btn-outline" onClick={() => showTasks(a.id)}
                        style={{ borderRadius: 8, padding: '2px 8px' }}>
                  {detail ? <ChevronDown size={13} strokeWidth={1.8} /> : <ChevronRight size={13} strokeWidth={1.8} />}
                </button>
                <b style={{ fontSize: 14 }}>{a.title}</b>
                <span style={chip('rgba(99,102,241,0.08)', 'var(--primary)')}>{a.subject_name}</span>
                {a.blocks.map(b => (
                  <span key={b.id}
                        style={chip(b.autocheck ? 'rgba(16,185,129,0.08)' : 'rgba(245,158,11,0.14)',
                                    b.autocheck ? '#065F46' : '#92400E')}>
                    {b.label} · {b.tasks}
                  </span>
                ))}
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  {a.tasks} задач · {a.students.length} уч.
                  {a.due_at ? ` · до ${String(a.due_at).slice(0, 16).replace('T', ' ')}` : ''}
                  {a.expired ? ' · срок вышел' : ''}
                </span>
                {a.status === 'draft' && <span style={chip('rgba(107,114,128,0.12)', '#374151')}>черновик</span>}
                {a.status === 'revoked' && <span style={chip('rgba(107,114,128,0.12)', '#374151')}>отозвано</span>}
                {a.status === 'active' && <span style={chip('rgba(16,185,129,0.12)', '#065F46')}>назначено</span>}
                <span style={{ marginLeft: 'auto', display: 'flex', gap: 8,
                               alignItems: 'flex-start' }}>
                  {a.status === 'draft' && (
                    <button className="btn btn-sm btn-primary" onClick={() => publish(a)}
                            style={{ borderRadius: 10, padding: '4px 12px' }}>
                      <Send size={12} strokeWidth={1.5} style={{ verticalAlign: -1, marginRight: 4 }} />Опубликовать
                    </button>
                  )}
                  {a.status === 'active' && (
                    <button className="btn btn-sm btn-outline"
                            onClick={() => setResults(r => (r === a.id ? null : a.id))}
                            style={{ borderRadius: 10, padding: '4px 12px' }}>
                      Результаты
                    </button>
                  )}
                  {a.status === 'active' && <GcLinkButton assignment={a} />}
                  {a.status !== 'revoked' && (
                    <button className="btn btn-sm btn-outline" onClick={() => revoke(a)}
                            style={{ borderRadius: 10, padding: '4px 12px', color: '#991B1B' }}>
                      <Undo2 size={12} strokeWidth={1.5} style={{ verticalAlign: -1, marginRight: 4 }} />Отозвать
                    </button>
                  )}
                </span>
              </div>
              {detail && (detail.blocks || []).map(b => (
                <div key={b.id}>
                  <div style={{ padding: '8px 20px', fontSize: 12, fontWeight: 600,
                                color: 'var(--text-secondary)', background: 'rgba(99,102,241,0.03)' }}>
                    {b.label} · {b.tasks} задач · {b.autocheck ? 'сверяет машина' : 'зачитывает человек'}
                  </div>
                  {(b.questions || []).map(q => <TaskRow key={q.id} q={q} picked={null} showAnswer />)}
                  {!b.questions && b.tasks > 0 && (
                    <div style={{ padding: '10px 20px', fontSize: 13, color: 'var(--text-secondary)' }}>
                      Список задач этого урока не дошёл — закройте и раскройте стрелку снова.
                    </div>
                  )}
                </div>
              ))}
              {results === a.id && <LessonResults assignment={a} />}
            </div>
          )
        })}
      </div>
    </div>
  )
}
