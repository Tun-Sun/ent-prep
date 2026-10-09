import { useState, useEffect } from 'react'
import { assignmentsAPI, subjectsAPI, groupsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import { ClipboardList, RefreshCw, AlertTriangle, ChevronDown, ChevronRight, Undo2 } from 'lucide-react'

const LEVELS = [['easy', 'Лёгкий'], ['medium', 'Средний'], ['hard', 'Сложный']]
const SOURCES = [['', 'Любой источник'], ['book_scan', 'Только оцифрованные из книг'],
                 ['collected', 'Только собранные'], ['authorial', 'Только авторские']]

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
  return Object.entries(d).map(([k, v]) => `${k}: ${[].concat(v).join(', ')}`).join(' · ')
}

const levelName = (v) => (LEVELS.find(([k]) => k === v) || [, v])[1]

// Строка набора: тот же рендер KaTeX, что в банке, плюс номер и страница из
// паспорта — по ним тренер находит задачу в книге, если ученик спросит про неё.
// `picked === null` — строка без галочки: так выглядит уже выданное назначение,
// где состав менять нельзя.
function TaskRow({ q, picked, onToggle }) {
  const pr = q.provenance || {}
  return (
    <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 12 }}>
      {picked !== null && (
        <input type="checkbox" checked={picked} title="Включить задачу в назначение"
               onChange={e => onToggle(e.target.checked)}
               style={{ width: 16, height: 16, accentColor: 'var(--primary)', cursor: 'pointer', marginTop: 3 }} />
      )}
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
          {pr.num && <span style={chip('rgba(37,99,235,0.1)', '#1E40AF')}>№ {pr.num}</span>}
          <span style={chip('rgba(16,185,129,0.08)', '#065F46')}>{q.topic_name}</span>
          <span style={chip('rgba(99,102,241,0.08)', 'var(--primary)')}>{levelName(q.difficulty)}</span>
          {(q.uncertain || []).length > 0 && (
            <span style={chip('rgba(239,68,68,0.1)', '#991B1B')}>
              <AlertTriangle size={11} strokeWidth={1.5} style={{ verticalAlign: -1 }} /> спорных знаков: {q.uncertain.length}
            </span>
          )}
          {pr.page && <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{pr.run} · с. {pr.page}</span>}
        </div>
        <div style={{ fontSize: 14 }}><FormattedText text={q.latex || q.text} markdown /></div>
      </div>
    </div>
  )
}

export default function AssignByLevelPage() {
  const [subjects, setSubjects] = useState([])
  const [subject, setSubject] = useState('')
  const [topic, setTopic] = useState('')
  const [topics, setTopics] = useState([])
  const [level, setLevel] = useState('easy')
  const [count, setCount] = useState(10)
  const [source, setSource] = useState('')
  const [rows, setRows] = useState([])
  const [checked, setChecked] = useState([])
  const [sizes, setSizes] = useState(null)
  const [pool, setPool] = useState(null)
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState('')
  const [done, setDone] = useState('')
  const [busy, setBusy] = useState(false)

  const [groups, setGroups] = useState([])
  const [group, setGroup] = useState('')
  const [needle, setNeedle] = useState('')
  const [students, setStudents] = useState([])
  const [to, setTo] = useState([])
  const [title, setTitle] = useState('')
  const [mine, setMine] = useState([])
  const [open, setOpen] = useState(null)

  const load = () => {
    if (!subject) { setRows([]); setChecked([]); setSizes(null); setPool(null); return }
    setLoading(true)
    setNotice('')
    const params = { subject, difficulty: level, count }
    if (topic) params.topic = topic
    if (source) params.source_type = source
    assignmentsAPI.pick(params)
      // порядок выдачи случайный на каждый запрос, поэтому выбор сбрасываем:
      // оставить галочки по id после «перемешать» значило бы снять их с других задач
      .then(res => {
        setRows(res.data.questions)
        setChecked(res.data.questions.map(q => q.id))
        setPool(res.data.pool)
        setSizes(res.data.levels)
      })
      .catch(e => { setRows([]); setChecked([]); setNotice(errorText(e)) })
      .finally(() => setLoading(false))
  }

  // count правят вводом: без паузы каждый символ — запрос к банку
  useEffect(() => {
    const t = setTimeout(load, 350)
    return () => clearTimeout(t)
  }, [subject, topic, level, count, source])

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

  const chosen = rows.filter(q => checked.includes(q.id))

  const assign = () => {
    if (!chosen.length || !to.length) return
    const whom = to.length === 1
      ? (students.find(s => s.id === to[0]) || {}).full_name || 'одному ученику'
      : `${to.length} ученикам`
    if (!confirm(`Назначить ${chosen.length} задач ${levelName(level).toLowerCase()} уровня — ${whom}?`)) return
    setBusy(true)
    setNotice('')
    setDone('')
    assignmentsAPI.create({
      title: title.trim() || `${(subjects.find(s => s.id === Number(subject)) || {}).name || ''} · ${levelName(level)}`.trim(),
      subject: Number(subject), difficulty: level,
      students: to, question_ids: chosen.map(q => q.id),
    })
      .then(res => {
        setDone(`Назначено · ${res.data.tasks} задач · ${res.data.students.length} уч.`)
        setMine([res.data, ...mine])
        setTitle('')
      })
      .catch(e => setNotice(errorText(e)))
      .finally(() => setBusy(false))
  }

  const revoke = (a) => {
    if (!confirm(`Отозвать «${a.title}»? Ученики перестанут его видеть, запись останется.`)) return
    setNotice('')
    assignmentsAPI.revoke(a.id)
      .then(res => setMine(ms => ms.map(m => (m.id === res.data.id ? res.data : m))))
      .catch(e => setNotice(errorText(e)))
  }

  const showTasks = (id) => {
    if (open && open.id === id) { setOpen(null); return }
    assignmentsAPI.detail(id).then(res => setOpen(res.data)).catch(e => setNotice(errorText(e)))
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          <ClipboardList size={18} strokeWidth={1.5} style={{ verticalAlign: -3, marginRight: 6 }} />
          Назначение по уровню
        </h1>
        <p className="page-subtitle">
          Домашнее собирается из банка по ступени сложности: предмет → уровень → сколько задач.
          Набор фиксируется в момент назначения, поэтому следующий перегон книги его не изменит.
          Черновики в набор не попадают — ученику уходит только принятое.
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
            <div style={label}>Уровень</div>
            <div style={{ display: 'flex', gap: 6 }}>
              {LEVELS.map(([v, n]) => (
                <button key={v} className={`btn btn-sm ${level === v ? 'btn-primary' : 'btn-outline'}`}
                        onClick={() => setLevel(v)}
                        disabled={!subject || (sizes && !sizes[v])}
                        title={sizes ? `в банке этого уровня: ${sizes[v]}` : 'сначала предмет'}
                        style={{ borderRadius: 10, padding: '6px 12px' }}>
                  {n}{sizes ? ` · ${sizes[v]}` : ''}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div style={label}>Сколько задач</div>
            <input type="number" min="1" max="50" value={count} style={{ ...sel, width: 90 }}
                   onChange={e => setCount(Math.max(1, Math.min(50, Number(e.target.value) || 1)))} />
          </div>
          <div>
            <div style={label}>Источник</div>
            <select value={source} onChange={e => setSource(e.target.value)} style={sel}>
              {SOURCES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
            </select>
          </div>
          <div>
            <div style={label}>Тема</div>
            <select value={topic} onChange={e => setTopic(e.target.value)} disabled={!subject} style={sel}>
              <option value="">Все темы</option>
              {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <button className="btn btn-sm btn-outline" onClick={load} disabled={!subject || loading}
                  title="Другой случайный набор того же уровня"
                  style={{ borderRadius: 10, padding: '6px 12px', marginBottom: 1 }}>
            <RefreshCw size={12} strokeWidth={1.5} style={{ verticalAlign: -1, marginRight: 4 }} />Перемешать
          </button>
        </div>
        {notice && <div style={{ marginTop: 10, fontSize: 13, color: '#991B1B' }}>{notice}</div>}
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 20 }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontSize: 13,
                      fontWeight: 600, color: 'var(--text-secondary)', display: 'flex', gap: 10, alignItems: 'center' }}>
          {subject ? `${levelName(level)} · задач под фильтр ${pool === null ? '…' : pool} · показано ${rows.length} · в наборе ${chosen.length}`
                   : 'Набор пока пуст: выберите предмет'}
          {rows.length > 0 && (
            <button className="btn btn-sm btn-outline" style={{ marginLeft: 'auto', borderRadius: 10, padding: '4px 12px' }}
                    onClick={() => setChecked(chosen.length === rows.length ? [] : rows.map(r => r.id))}>
              {chosen.length === rows.length ? 'Снять все' : 'Выбрать все'}
            </button>
          )}
        </div>
        {loading ? (
          <div className="text-center py-4"><div className="spinner"></div></div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 30, color: 'var(--text-secondary)', fontSize: 13 }}>
            Под этот уровень и фильтр принятых задач нет. Смените уровень, источник или число задач.
          </div>
        ) : rows.map(q => (
          <TaskRow key={q.id} q={q} picked={checked.includes(q.id)}
                   onToggle={on => setChecked(rs => on ? [...rs, q.id] : rs.filter(i => i !== q.id))} />
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
                                     alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ minWidth: 240 }}>
          <div style={label}>Название</div>
          <input value={title} onChange={e => setTitle(e.target.value)} style={{ ...sel, width: '100%', cursor: 'text' }}
                 placeholder={`${(subjects.find(s => s.id === Number(subject)) || {}).name || ''} · ${levelName(level)}`} />
        </div>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
          {chosen.length} задач · {to.length} уч.
        </span>
        <button className="btn btn-primary" onClick={assign} disabled={!chosen.length || !to.length || busy}
                style={{ marginLeft: 'auto', borderRadius: 10, padding: '8px 16px' }}>
          {busy ? 'Назначаю…' : `Назначить${chosen.length ? ` ${chosen.length} задач` : ''}`}
        </button>
        {done && <span style={{ fontSize: 13, color: '#065F46' }}>{done}</span>}
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontSize: 13,
                      fontWeight: 600, color: 'var(--text-secondary)' }}>
          Выданные назначения · {mine.length}
        </div>
        {!mine.length && (
          <div style={{ padding: 30, color: 'var(--text-secondary)', fontSize: 13 }}>
            Назначений ещё нет.
          </div>
        )}
        {mine.map(a => (
          <div key={a.id} style={{ borderBottom: '1px solid var(--border)' }}>
            <div style={{ padding: '14px 20px', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <button className="btn btn-sm btn-outline" onClick={() => showTasks(a.id)}
                      style={{ borderRadius: 8, padding: '2px 8px' }}>
                {open && open.id === a.id ? <ChevronDown size={13} strokeWidth={1.8} /> : <ChevronRight size={13} strokeWidth={1.8} />}
              </button>
              <b style={{ fontSize: 14 }}>{a.title}</b>
              <span style={chip('rgba(99,102,241,0.08)', 'var(--primary)')}>{a.subject_name}</span>
              <span style={chip('rgba(16,185,129,0.08)', '#065F46')}>{a.difficulty_display}</span>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {a.tasks} задач · {a.students.map(s => s.full_name || s.username).join(', ')}
              </span>
              {a.status === 'revoked' && <span style={chip('rgba(107,114,128,0.12)', '#374151')}>отозвано</span>}
              {a.status === 'active' && (
                <button className="btn btn-sm btn-outline" onClick={() => revoke(a)}
                        style={{ marginLeft: 'auto', borderRadius: 10, padding: '4px 12px', color: '#991B1B' }}>
                  <Undo2 size={12} strokeWidth={1.5} style={{ verticalAlign: -1, marginRight: 4 }} />Отозвать
                </button>
              )}
            </div>
            {open && open.id === a.id && (
              <div>
                {open.questions.map(q => <TaskRow key={q.id} q={q} picked={null} />)}
                {!open.questions.length && (
                  <div style={{ padding: '10px 20px', fontSize: 13, color: 'var(--text-secondary)' }}>
                    Задач в назначении нет.
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
