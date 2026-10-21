import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { myAssignmentsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import { leaveDemoSession, savedReturnSession } from '../auth/lessonPreview'
import { ClipboardList, ArrowLeft, Inbox, Check, ChevronLeft, ChevronRight, Lock } from 'lucide-react'

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

// Сданный блок для ученика закрыт: экран не даёт ни править, ни сдавать его заново.
const SENT_STATES = ['submitted', 'reviewed']
const isSent = (b) => SENT_STATES.includes(b.state)

// «3 балла», «21 балл», «12 баллов» — экран ученика читает человек, а не машина
const plural = (n, one, few, many) => {
  const t = n % 10, h = n % 100
  if (t === 1 && h !== 11) return `${n} ${one}`
  if ([2, 3, 4].includes(t) && ![12, 13, 14].includes(h)) return `${n} ${few}`
  return `${n} ${many}`
}
const points = (n) => plural(n, 'балл', 'балла', 'баллов')
const tasks = (n) => plural(n, 'задача', 'задачи', 'задач')

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

// Навигация по шагам: ребёнок видит один блок за раз и всегда знает, сколько блоков
// уже сдано. Сданный блок отмечается зелёной галочкой и остаётся доступным только
// для чтения — нажимать «Сдать» повторно там уже нечего.
//
// Кружочки с цифрами отсюда убраны намеренно: на телефоне `1 2 3 4` вкладок стояли
// прямо над `1 лёгкий`, `2 лёгкий` из нумерации задач, и ребёнок не находил, где
// начинается список. Теперь вкладки — сетка на контрастной подложке, а цифра живёт
// только у задач.
const LONG_DEFAULT = { in_class: 'Классная работа' }

// Типовое имя блока на узком экране переносилось на две строки и ломало сетку 2×2.
// Название, заданное тренером, экран не сокращает: оно его, а не машинное.
const tabName = (b) => (LONG_DEFAULT[b.kind] && b.label === LONG_DEFAULT[b.kind])
  ? 'Классная'
  : b.label

function BlockTabs({ blocks, activeId, onPick }) {
  const done = blocks.filter(isSent).length
  return (
    <div className="card" style={{ padding: 12, marginBottom: 16 }}>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
        сдано {done} из {blocks.length}
      </div>
      <div className="block-tabs-shell">
        <div className="block-tabs">
          {blocks.map(b => {
            const sent = isSent(b)
            const current = b.id === activeId
            const cls = 'block-tab' + (current ? ' is-active' : '') + (sent ? ' is-sent' : '')
            return (
              <button key={b.id} className={cls} onClick={() => onPick(b.id)}
                      aria-current={current ? 'page' : undefined}>
                <span className="block-tab-name">{tabName(b)}</span>
                <span className="block-tab-badge">
                  {sent ? <><Check size={11} strokeWidth={2.5} /> Сдано</> : tasks(b.tasks)}
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// Литеры, которые движок уже видит в строке: `B, G`, `BG` и `b g` для него один
// ответ, поэтому подсветка чипов обязана считать так же, а не по запятым.
const lettersIn = (raw) => String(raw || '').toUpperCase().match(/[A-H]/g) || []

// Чем кнопка вставляет, тем и сверяет автопроверка: `√(3)` движок читает как текст и
// отдаёт pending_review, а `sqrt(3)` — решает; литеру `π` в ответе он теряет, `pi` —
// нет. Поэтому на кнопке остаётся тот знак, который ребёнок узнаёт, а в поле
// приезжает тот, который понимает движок.
const SYMBOLS = [
  { label: '/', insert: '/' },
  { label: '^', insert: '^' },
  { label: '·10^-', insert: '·10^-' },
  { label: '√', insert: 'sqrt()', caret: -1 },
  { label: 'π', insert: 'pi' },
  { label: ':', insert: ':' },
  { label: ';', insert: ';' },
  { label: '=', insert: '=' },
  { label: '−', insert: '−' },
]

// Прежнее «Решение и ответ — как в тетради» стояло над всеми полями и сбивало: в
// автопроверяемом блоке ребёнок переписывал с телефона весь ход решения, которое
// машина сверять не умеет, а ждёт она одну строку ответа.
const placeholderFor = (block, q) => {
  if (q.options && q.options.length) return 'Нажми букву варианта — или впиши её'
  return block.autocheck
    ? 'Введите только ответ (например: 6 или 3/4 или 4,9*10^-18)'
    : 'Краткий ответ или итог решения'
}

export default function MyAssignmentsPage() {
  const [items, setItems] = useState([])
  const [lesson, setLesson] = useState(null)
  const [activeId, setActiveId] = useState(0)
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
  // самое свежее, что ребёнок набрал или нажал, — синхронно, до перерисовки: по нему
  // чипы и панель символов понимают, что отправлять, и что досохранить, пока сервер
  // ещё отвечает на предыдущее нажатие
  const draftRef = useRef({})
  const areaRef = useRef({})

  // После сдачи ребёнок не обязан сам искать, куда идти дальше: экран сам переходит
  // к первому несданному блоку, а когда сдано всё — остаётся на месте и смотрит итог.
  const nextOpen = (blocks, justSent) => {
    const i = blocks.findIndex(b => b.id === justSent)
    const ahead = blocks.slice(i + 1).concat(blocks.slice(0, Math.max(i, 0)))
    const open = ahead.find(b => !isSent(b))
    return open ? open.id : (blocks[i] || blocks[0] || {}).id || 0
  }

  const open = (id, sentMsg = '', keepActive = 0) => {
    setLoading(true)
    setNotice('')
    setAskBlock(0)
    myAssignmentsAPI.detail(id)
      .then(res => {
        setLesson(res.data)
        setSent(sentMsg)
        const blocks = res.data.blocks
        const wanted = keepActive || (blocks.find(b => !isSent(b)) || blocks[0] || {}).id || 0
        setActiveId(wanted)
        // черновик поля = то, что уже сохранено: правка прежнего ответа не должна
        // выглядеть как пустая строка
        const saved = {}
        const byQ = {}
        blocks.forEach(b => b.answers.forEach(a => {
          saved[a.question] = a.raw_answer
          byQ[a.question] = a
        }))
        setDrafts(saved)
        // ref — отдельный объект: `setDraft` дописывает его на месте, и если бы он
        // делил ссылку с `baseline`, тап по варианту сам себе «сохранял» ответ
        // ещё до запроса на сервер
        draftRef.current = { ...saved }
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

  // `silent` — путь onBlur, чипа и сдачи: сохранение идёт тихо, без кнопки «Сохраняю…»,
  // а ученик видит только «Сохранено ✓». `rawArg` приходит от тапа по варианту: поле
  // обновлено только что, и ждать перерисовки, чтобы прочитать его, нельзя.
  const save = (block, q, silent, rawArg) => {
    const raw = rawArg === undefined ? (drafts[q.id] || '') : rawArg
    // `rawArg === ''` — ответ сняли чипом: его обязан отпустить и сервер, иначе
    // прежние буквы дожили бы до перезагрузки экрана. Клавиатурную правку «в никуда»
    // сохранять нечем.
    if (raw === (baseline[q.id] || '')) return Promise.resolve(false)
    if (raw.trim() === '' && rawArg !== '') return Promise.resolve(false)
    if (!silent) setBusy(q.id)
    setNotice('')
    return myAssignmentsAPI.answer(lesson.id, { block: block.id, question: q.id, raw_answer: raw })
      .then(res => {
        setAnswers(prev => ({ ...prev, [q.id]: { ...prev[q.id], ...res.data, question: q.id } }))
        setBaseline(prev => ({ ...prev, [q.id]: raw }))
        setTicks(prev => ({ ...prev, [q.id]: true }))
        // ребёнок успел нажать ещё раз, пока сервер отвечал на предыдущее: иначе
        // на экране останется одно, а на сервере — другое
        const latest = draftRef.current[q.id] || ''
        if (latest !== raw) return save(block, q, true, latest)
        return true
      })
      .catch(e => { setNotice(errorText(e)); return false })
      .finally(() => { if (!silent) setBusy(0) })
  }

  // Черновик пишется в ref синхронно: по нему чипы решают, что отправлять, в тот же
  // миг, когда React ещё рисует прошлое состояние.
  const setDraft = (qid, value) => {
    draftRef.current[qid] = value
    setDrafts(d => ({ ...d, [qid]: value }))
  }

  // Тап по букве варианта — это ответ: движок сверяет тест набором литер, поэтому
  // `B` и `B, G` здесь две разные команды, а не дописывание текста.
  const pickLetter = (block, q, letter) => {
    const picked = new Set(lettersIn(draftRef.current[q.id] || ''))
    if (picked.has(letter)) picked.delete(letter)
    else picked.add(letter)
    const raw = Array.from(picked).sort().join(', ')
    setDraft(q.id, raw)
    save(block, q, true, raw)
  }

  // Знак вставляется в позицию курсора, а не в конец: ребёнок правит `4,9·10^-18`
  // посередине, и кнопка не имеет права переписывать ему ответ.
  const insertSymbol = (qid, snippet, caretShift) => {
    const area = areaRef.current[qid]
    const raw = draftRef.current[qid] || ''
    const from = area ? area.selectionStart : raw.length
    const to = area ? area.selectionEnd : raw.length
    setDraft(qid, raw.slice(0, from) + snippet + raw.slice(to))
    const caret = from + snippet.length + (caretShift || 0)
    // после смены controlled-значения карета уезжает в конец — возвращаем её на место
    if (area) requestAnimationFrame(() => { area.focus(); area.setSelectionRange(caret, caret) })
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
          .then(() => open(lesson.id, `Блок «${block.label}» сдан.`, nextOpen(lesson.blocks, block.id)))
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

  const blocks = lesson.blocks
  const block = blocks.find(b => b.id === activeId) || blocks[0]
  const index = blocks.findIndex(b => b.id === block.id)
  const prev = index > 0 ? blocks[index - 1] : null
  const next = index >= 0 && index < blocks.length - 1 ? blocks[index + 1] : null
  const locked = lesson.expired || isSent(block)
  const p = block.progress

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
      ) : (
        <>
          <BlockTabs blocks={blocks} activeId={block.id} onPick={setActiveId} />

          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex',
                          gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <b style={{ fontSize: 17 }}>{block.label} · {tasks(block.tasks)}</b>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {block.autocheck ? 'проверяет машина сразу' : 'зачитывает преподаватель'}
              </span>
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center',
                             flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                {p && p.total ? (
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    решено {p.checked} из {p.total}
                    {p.percent !== null ? ` · ${p.percent} %` : ''}
                    {p.pending ? ` · на проверке ${p.pending}` : ''}
                  </span>
                ) : null}
                {isSent(block) ? (
                  <span style={{ ...chip('rgba(16,185,129,0.14)', '#065F46'), fontSize: 13,
                                padding: '8px 14px', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <Check size={15} strokeWidth={2.5} /> Блок сдан
                  </span>
                ) : askBlock === block.id ? (
                  <>
                    <span style={{ fontSize: 13 }}>Ответы будут отправлены. Сдаём?</span>
                    <button className="btn btn-primary" onClick={() => flushAndSubmit(block)}
                            disabled={flushing || busy === -1}
                            style={{ borderRadius: 10, padding: '10px 20px', fontSize: 15 }}>
                      {flushing ? 'Сохраняю ответы…' : busy === -1 ? 'Сдаю…' : 'Да, сдать'}
                    </button>
                    <button className="btn btn-outline" onClick={() => setAskBlock(0)}
                            style={{ borderRadius: 10, padding: '10px 18px', fontSize: 15 }}>
                      Отмена
                    </button>
                  </>
                ) : (
                  <button className="btn btn-primary" onClick={() => setAskBlock(block.id)}
                          disabled={lesson.expired || flushing || busy === -1}
                          style={{ borderRadius: 12, padding: '12px 30px', fontSize: 16 }}>
                    {flushing ? 'Сохраняю ответы…' : busy === -1 ? 'Сдаю…' : 'Сдать блок'}
                  </button>
                )}
              </span>
            </div>

            {lesson.expired && !isSent(block) && (
              <div style={{ padding: '10px 20px', fontSize: 13, color: '#991B1B',
                            background: 'rgba(239,68,68,0.06)', borderBottom: '1px solid var(--border)' }}>
                Срок сдачи вышел: блок закрыт, ответы больше не принимаются.
              </div>
            )}
            {isSent(block) && (
              <div style={{ padding: '10px 20px', fontSize: 13, color: '#065F46',
                            background: 'rgba(16,185,129,0.07)', borderBottom: '1px solid var(--border)',
                            display: 'flex', gap: 8, alignItems: 'center' }}>
                <Lock size={14} strokeWidth={2} /> Блок сдан — он закрыт для правки. Ниже ваши ответы
                и вердикты{block.autocheck ? ', а у решённых задач — разбор.' : '.'}
              </div>
            )}

            {block.questions.map((q, i) => {
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
                  {!!(q.options && q.options.length) && (
                    <div className="option-chips">
                      {q.options.map(letter => (
                        <button key={letter} type="button" disabled={locked}
                                className={'option-chip' +
                                  (lettersIn(drafts[q.id]).includes(letter) ? ' is-on' : '')}
                                onMouseDown={e => e.preventDefault()}
                                onClick={() => pickLetter(block, q, letter)}>
                          {letter}
                        </button>
                      ))}
                    </div>
                  )}
                  <textarea ref={el => { areaRef.current[q.id] = el }}
                            value={drafts[q.id] || ''} disabled={locked}
                            onChange={e => setDraft(q.id, e.target.value)}
                            onBlur={() => { if (!locked && dirtyFor(q.id)) save(block, q, true) }}
                            placeholder={placeholderFor(block, q)} rows={block.autocheck ? 2 : 3}
                            style={{ width: '100%', marginTop: 10, borderRadius: 10, padding: 10, fontSize: 13,
                                     border: '1px solid var(--border)', fontFamily: 'inherit', resize: 'vertical',
                                     background: locked ? 'rgba(107,114,128,0.06)' : '#fff' }} />
                  {/* Панель символов нужна только там, где ответ печатают: тестовые
                      буквы ребёнок уже нажал, а поле под ними только для своих знаков. */}
                  {!locked && !(q.options && q.options.length) && (
                    <div className="symbol-bar">
                      {SYMBOLS.map(s => (
                        <button key={s.label} type="button" className="symbol-btn"
                                onMouseDown={e => e.preventDefault()}
                                onClick={() => insertSymbol(q.id, s.insert, s.caret)}>
                          {s.label}
                        </button>
                      ))}
                    </div>
                  )}
                  {!locked && (
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
                      <button className="btn btn-sm btn-outline" onClick={() => save(block, q)}
                              disabled={!(drafts[q.id] || '').trim() || busy === q.id}
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
                  )}
                  {a && (a.feedback || {}).etalon && (
                    <div style={{ marginTop: 8, fontSize: 13 }}>
                      <b style={{ fontSize: 11, color: 'var(--text-secondary)' }}>ПРАВИЛЬНЫЙ ОТВЕТ · </b>
                      <FormattedText text={(a.feedback || {}).etalon} markdown />
                    </div>
                  )}
                  {/* Разбор страницы сервер не отдаёт, пока блок не сдан, поэтому здесь
                      он появляется сам и свёрнутым: ученик решает смотреть или нет. */}
                  {q.solution_latex && (
                    <details style={{ marginTop: 10, border: '1px solid var(--border)',
                                      borderRadius: 10, padding: '6px 10px' }}>
                      <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 600,
                                        color: 'var(--primary)', userSelect: 'none' }}>
                        Показать разбор
                      </summary>
                      <div style={{ marginTop: 8, fontSize: 13 }}>
                        <FormattedText text={q.solution_latex} markdown />
                      </div>
                    </details>
                  )}
                </div>
              )
            })}
            {!block.questions.length && (
              <div style={{ padding: 20, fontSize: 13, color: 'var(--text-secondary)' }}>В блоке нет задач.</div>
            )}

            <div style={{ padding: '14px 20px', display: 'flex', gap: 10, justifyContent: 'space-between' }}>
              <button className="btn btn-sm btn-outline" onClick={() => setActiveId(prev.id)} disabled={!prev}
                      style={{ borderRadius: 10, padding: '8px 14px' }}>
                <ChevronLeft size={14} strokeWidth={2} style={{ verticalAlign: -2 }} />
                {prev ? prev.label : ''}
              </button>
              {next ? (
                <button className="btn btn-sm btn-primary" onClick={() => setActiveId(next.id)}
                        style={{ borderRadius: 10, padding: '8px 14px' }}>
                  {next.label}
                  <ChevronRight size={14} strokeWidth={2} style={{ verticalAlign: -2 }} />
                </button>
              ) : <span />}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
