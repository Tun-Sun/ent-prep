import { useState, useEffect } from 'react'
import { questionsAPI, subjectsAPI } from '../../api'
import FormattedText from '../../components/FormattedText'
import { BookOpen, AlertTriangle, HelpCircle, Pencil, Trash2, Search } from 'lucide-react'

// зеркалит QuestionPagination на бэкенде: менять надо вместе с ним
const PAGE_SIZE = 50
const DIFFICULTY = [['easy', 'Лёгкий'], ['medium', 'Средний'], ['hard', 'Сложный']]
const STATUS = [['draft', 'Черновик'], ['verified', 'Проверено'], ['rejected', 'Отклонено']]
// один список подписей и для селекта, и для строки «что именно я принял»
const FORMAT = [['', 'Любой формат'], ['задача,теория', 'Задачи и теория — без тестов'],
                ['задача', 'Только задачи'], ['тест', 'Только тесты с вариантами'],
                ['теория', 'Только теория']]
// Класс школьной программы, к которому задачу относит тренер. Книга его не печатает,
// поэтому «без класса» — отдельный выбор: это не «неизвестный класс 5», это «ещё не решено».
const GRADE_FILTER = [['', 'Любой класс'], ['none', 'Класс не проставлен'],
                      ...[5, 6, 7, 8, 9, 10, 11].map(g => [String(g), `${g} класс`])]
const GRADES = [5, 6, 7, 8, 9, 10, 11]
// Язык строки. Перевод — это отдельная строка банка, а не правка русской, поэтому
// «показать казахские условия» должен уметь и экран, и фильтр под пакетную приёмку.
const LANGUAGE = [['', 'Любой язык'], ['ru', 'Русский (ru)'], ['kk', 'Қазақша (kk)']]

const chip = (bg, color) => ({
  padding: '2px 8px', borderRadius: 100, fontSize: 11, fontWeight: 600, background: bg, color,
})

// Книжный блок печатает ответы не под задачей, а списком в своём конце, и порядок в
// этом списке — по напечатанному номеру: «10» идёт за «9», а не за «1», как по буквам.
const numKey = (num) => String(num || '').split(/\D+/).filter(Boolean).map(Number)
const inBookOrder = (a, b) => {
  const x = numKey((a.provenance || {}).num)
  const y = numKey((b.provenance || {}).num)
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] === undefined ? 1e9 : x[i]) - (y[i] === undefined ? 1e9 : y[i])
    if (d) return d
  }
  return a.id - b.id
}

// Доска ответов темы: те же данные, что лежат в строках (их правят в окне «Править»),
// но собранные так, как их напечатал составитель — под последним условием блока.
function AnswersBoard({ items }) {
  // Теоретический лист — не задача с ответом: его «номер» в паспорте это страница,
  // и в доске он выглядел бы как «12) —» там, где книга ничего не обещала.
  const tasks = items.filter(q => (q.provenance || {}).format !== 'теория')
  const sorted = [...tasks].sort(inBookOrder)
  const missed = sorted.filter(q => !(q.latex_answer || '').trim()).length
  if (!sorted.length) return null
  return (
    <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', background: 'rgba(245,158,11,0.05)' }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 8 }}>
        {/* без этой строки пустой ответ читался бы как потеря при оцифровке, хотя в
            источнике ответа нет — карточка задачи больше его не показывает */}
        ОТВЕТЫ · {sorted.length} строк{missed ? ` · без ответа ${missed}` : ''}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 18px', fontSize: 13 }}>
        {sorted.map(q => {
          const pr = q.provenance || {}
          const ans = (q.latex_answer || '').trim()
          return (
            <span key={q.id} style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
              <b style={{ color: '#92400E' }}>{pr.num ? `${pr.num})` : '—)'}</b>
              {pr.level && <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{pr.level}</span>}
              {ans
                ? <FormattedText text={ans} markdown />
                : <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    {pr.answer_note || 'в источнике ответа нет'}
                  </span>}
            </span>
          )
        })}
      </div>
    </div>
  )
}

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

function EditModal({ q, subjects, onClose, onSaved }) {
  const [latex, setLatex] = useState(q.latex || '')
  const [answer, setAnswer] = useState(q.latex_answer || '')
  const [difficulty, setDifficulty] = useState(q.difficulty || 'medium')
  const [grade, setGrade] = useState(q.grade ?? '')
  const [status, setStatus] = useState(q.verification_status || 'draft')
  const [subject, setSubject] = useState(q.subject)
  const [topics, setTopics] = useState([])
  const [topic, setTopic] = useState(q.topic)
  const [newTopic, setNewTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [showOriginal, setShowOriginal] = useState(false)
  const orig = (q.provenance || {}).ocr_original || {}
  const pr = q.provenance || {}
  // Вычитка — это сравнение с источником, а не с самим собой: без страницы скана
  // правая колонка показывает то же, что левая, только красивее.
  const pages = q.source_pages || []

  // Книги кончаются, а отрывки и рукописные задачи начинаются: место задачи
  // (предмет → тема) тренер правит здесь же, где опечатку.
  useEffect(() => {
    subjectsAPI.topics(subject).then(res => {
      setTopics(res.data)
      if (!res.data.some(t => t.id === Number(topic))) setTopic('')
    })
  }, [subject])

  // Откат держим модалку открытой: вернули машинный текст — и правим дальше по нему.
  const revert = () => {
    setBusy(true)
    setErr('')
    questionsAPI.revertOcr(q.id)
      .then(res => {
        if (!res.data.restored) { setErr('Откатывать нечего: оригинала из оцифровки в паспорте нет.'); return }
        const d = res.data.question
        setLatex(d.latex || '')
        setAnswer(d.latex_answer || '')
        onSaved(d)
      })
      .catch(e => setErr(errorText(e)))
      .finally(() => setBusy(false))
  }

  const save = () => {
    setBusy(true)
    setErr('')
    const named = newTopic.trim()
    const place = named ? subjectsAPI.createTopic({ name: named, subject }).then(r => r.data.id)
      : Promise.resolve(topic ? Number(topic) : null)
    place
      .then(tid => {
        const body = { latex, latex_answer: answer, difficulty, verification_status: status,
                       grade: grade === '' ? null : Number(grade) }
        if (tid) body.topic = tid
        return questionsAPI.patchBookScan(q.id, body)
      })
      .then(res => { onSaved(res.data); onClose() })
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
            {pr.review_note && (
              // Заметка — вывод глаз по скану, а не машинный флаг: строка остаётся
              // черновиком, и без неё следующий правщик заново спотыкается о тот же спор.
              <div style={{ fontSize: 12, lineHeight: 1.45, padding: '8px 10px', borderRadius: 8,
                            background: 'rgba(217,119,6,0.08)', border: '1px solid rgba(217,119,6,0.25)',
                            color: '#92400E' }}>
                <b>Заметка вычитки.</b> {pr.review_note}
                {pr.review_by ? ` — ${pr.review_by}` : ''}
              </div>
            )}
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
                <div style={label}>Предмет</div>
                <select style={pick} value={subject} onChange={e => setSubject(Number(e.target.value))}>
                  {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              <div style={{ flex: 1.4 }}>
                <div style={label}>Тема (книга · раздел)</div>
                <select style={pick} value={topic} onChange={e => setTopic(e.target.value)}>
                  <option value="">— перенести нельзя, выбери тему —</option>
                  {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
            </div>
            <div>
              <div style={label}>…или новая тема</div>
              <input style={{ ...pick, height: 38 }} placeholder="напр. Отрывок: задачи МКТ, вариант тренеровки"
                     value={newTopic} onChange={e => setNewTopic(e.target.value)} />
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={label}>Сложность</div>
                <select style={pick} value={difficulty} onChange={e => setDifficulty(e.target.value)}>
                  {DIFFICULTY.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <div style={label}>Класс</div>
                {/* пустая строка — «не решено», а не «снять с 9-го в бездну»: её
                    сериализатор читает как null, и отметка снимается честно */}
                <select style={pick} value={grade} onChange={e => setGrade(e.target.value)}>
                  <option value="">— не задан —</option>
                  {GRADES.map(g => <option key={g} value={g}>{g} класс</option>)}
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
                <button className="btn btn-sm btn-outline" onClick={revert} disabled={busy}
                        style={{ marginLeft: 8 }} title="Вернуть условие и ответ к машинному тексту">
                  Вернуть как в оцифровке
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
          {/* Вычитка — это сравнение с источником, поэтому скан страницы живёт
              рядом с полем условия, а не в отдельной вкладке стенда. */}
          <div style={{ minWidth: 0, gridColumn: '1 / -1' }}>
            <div style={label}>
              {pages.length > 1 ? 'Страницы источника' : 'Страница источника'} — {(q.provenance || {}).run || ''}
            </div>
            {pages.length ? (
              // Страницы друг под другом, а не в строку: разворот 1242 px в три
              // колонки сжимается в нечитаемую полосу, а сверять нужно именно текст.
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {pages.map(u => (
                  <a key={u} href={u} target="_blank" rel="noreferrer"
                     title="Открыть скан в полную величину"
                     style={{ display: 'block' }}>
                    <img src={u} alt=""
                         onError={e => { e.target.style.display = 'none' }}
                         style={{ width: '100%', height: 'auto', display: 'block',
                                  border: '1px solid var(--border)', borderRadius: 10,
                                  background: '#f7f7f8' }} />
                  </a>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                Страниц прогона здесь нет — сверять глазами пока не с чем.
              </div>
            )}
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
  const [filterDifficulty, setFilterDifficulty] = useState('')
  const [filterGrade, setFilterGrade] = useState('')
  const [filterLanguage, setFilterLanguage] = useState('')
  // чип «Переводы на проверке»: строки, у которых в паспорте есть исходник. Включая
  // его, переводим и статус на черновик — очередь смотрит только не принятые переводы
  const [filterTranslated, setFilterTranslated] = useState(false)
  // тесты без ключа ответа в общем списке только мешают вычитке задач —
  // по умолчанию показываем задачи и теорию, тесты под отдельным фильтром
  const [filterFormat, setFilterFormat] = useState('задача,теория')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  // Поиск по банку — подстрока: «где ещё у нас встречается этот знак». Без паузы
  // каждый ввод запрос к БД, а печатают по-казахски длинными словами.
  const [needle, setNeedle] = useState('')
  const [loading, setLoading] = useState(true)
  // Пакетная приёмка: выбор живёт в id, а не в объектах — строки перечитываются
  // фильтром, и в выбранном обязаны остаться именно те задачи, что на экране.
  const [picked, setPicked] = useState([])
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState('')
  const [editing, setEditing] = useState(null)
  const [notice, setNotice] = useState('')
  // Прогресс вычитки считаем по всему банку, а не по текущему фильтру: человеку
  // надо знать, сколько из 330 строк вообще просмотрено глазами.
  const [progress, setProgress] = useState(null)
  // Сколько строк под текущим фильтром ещё не принято. Без этого числа кнопка
  // «принять все» показывает всю выдачу и висит нетронутой после приёма всего.
  const [pending, setPending] = useState(null)
  // Очередь переводов считается по всему банку, а не по фильтру: человеку нужно
  // знать, сколько казахских строк вообще ждут глаза, а не сколько на этой странице.
  const [transQueue, setTransQueue] = useState(null)
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const loadProgress = () => {
    questionsAPI.list({ source_type: 'book_scan', page_size: 1 })
      .then(a => questionsAPI.list({ source_type: 'book_scan', verification_status: 'verified', page_size: 1 })
        .then(b => setProgress({ total: a.data.count, verified: b.data.count })))
      .catch(() => setProgress(null))
  }

  useEffect(() => { loadProgress(); loadPending(); loadTransQueue() }, [])

  useEffect(() => {
    subjectsAPI.list().then(res => setSubjects(res.data))
  }, [])

  useEffect(() => {
    if (filterSubject) subjectsAPI.topics(filterSubject).then(res => setTopics(res.data))
    else setTopics([])
  }, [filterSubject])

  // Один источник параметров для списка и для пакетной приёмки: «принять всё под
  // фильтр» обязано взять ровно те строки, что человек видит, а не пересказ фильтра.
  const queryParams = (pg = null) => {
    const params = { source_type: 'book_scan' }
    if (pg) params.page = pg
    if (filterSubject) params.subject = filterSubject
    if (filterTopic) params.topic = filterTopic
    if (filterStatus) params.verification_status = filterStatus
    if (filterDifficulty) params.difficulty = filterDifficulty
    if (filterGrade) params.grade = filterGrade
    if (filterLanguage) params.language = filterLanguage
    if (filterTranslated) params.translated = '1'
    if (filterFormat) params.task_format = filterFormat
    if (needle.trim()) params.q = needle.trim()
    return params
  }

  // Статус в фильтре перекрываем на черновик: «сколько осталось принять» — это
  // про текущий предмет/тему/формат/поиск, а не про то, что сейчас на экране.
  const loadPending = () => {
    questionsAPI.list({ ...queryParams(), verification_status: 'draft', page_size: 1 })
      .then(res => setPending(res.data.count))
      .catch(() => setPending(null))
  }

  const loadTransQueue = () => {
    questionsAPI.list({ source_type: 'book_scan', translated: '1',
                        verification_status: 'draft', page_size: 1 })
      .then(res => setTransQueue(res.data.count))
      .catch(() => setTransQueue(null))
  }

  const load = (pg = 1) => {
    setLoading(true)
    // с новой выдачей прежний выбор повесил бы приёмку на другие строки
    setPicked([])
    setNotice('')
    setDone('')
    questionsAPI.list(queryParams(pg))
      .then(res => { setRows(res.data.results || []); setTotal(res.data.count || 0) })
      .catch(e => {
        // пустой список из-за ошибки сети выглядит как «под фильтр ничего не попало»:
        // человек решит, что задач нет, хотя запрос просто упал
        setRows([]); setTotal(0); setNotice(errorText(e))
      })
      .finally(() => setLoading(false))
  }

  // Фильтры и поиск — один путь: страница всегда откатывается на первую, а запрос
  // уходит после паузы, иначе каждый символ — это прогон по 330 строкам.
  useEffect(() => {
    const t = setTimeout(() => { setPage(1); load(1); loadPending() }, 350)
    return () => clearTimeout(t)
  }, [filterSubject, filterTopic, filterStatus, filterDifficulty, filterGrade,
      filterLanguage, filterTranslated, filterFormat, needle])

  const goPage = (pg) => { setPage(pg); load(pg) }

  // Очередь смотрит НЕ принятые переводы, поэтому чип ставит и статус: иначе под
  // надписью «на проверке» показали бы строки, которые уже приняли. Когда черновых
  // переводов нет, кнопка гаснет, но остаётся видимой — по ней видно, что очередь пуста,
  // а не что фильтра нет; все казахские строки смотрятся селектором «Язык».
  const toggleTranslated = () => {
    if (filterTranslated) { setFilterTranslated(false); return }
    setFilterTranslated(true)
    setFilterStatus('draft')
  }

  const remove = (q) => {
    const pr = q.provenance || {}
    const what = `${pr.format === 'тест' ? 'тест' : (pr.unit || 'задача')}${pr.page ? ` · с. ${pr.page}` : ''}${pr.run ? ` из «${pr.run}»` : ''}`
    if (!confirm(`Удалить ${what} из банка? Вернуть можно только повторным импортом прогона.`)) return
    setNotice('')
    questionsAPI.delete(q.id)
      .then(() => {
        setRows(rs => rs.filter(r => r.id !== q.id)); setTotal(t => t - 1)
        // удалённый перевод больше не в очереди — число на чипе обязано сдвинуться
        loadTransQueue()
      })
      .catch(e => setNotice(errorText(e)))
  }

  // Что именно принимает человек — надо написать в диалоге числом и фильтром:
  // «принять всё» без адреса отличило бы 330 строк от 15 недосмотренных.
  const filterNote = () => {
    const named = [
      filterSubject && (subjects.find(s => s.id === Number(filterSubject)) || {}).name,
      filterTopic && (topics.find(t => t.id === Number(filterTopic)) || {}).name,
      filterStatus && (STATUS.find(([v]) => v === filterStatus) || [, ''])[1],
      filterDifficulty && (DIFFICULTY.find(([v]) => v === filterDifficulty) || [, ''])[1],
      filterGrade && (GRADE_FILTER.find(([v]) => v === filterGrade) || [, ''])[1],
      filterLanguage && (LANGUAGE.find(([v]) => v === filterLanguage) || [, ''])[1],
      filterTranslated && 'только переводы',
      filterFormat && (FORMAT.find(([v]) => v === filterFormat) || [, filterFormat])[1],
      needle.trim() && `поиск «${needle.trim()}»`,
    ].filter(Boolean)
    return named.length ? named.join(' · ') : 'весь банк'
  }

  // Приёмку ставит человек — кнопка здесь только экономит его клики: статус сразу
  // по выбранному или по всей выдаче, вместо окна «Править» на каждую задачу.
  const bulk = (to, whole) => {
    const n = whole ? pending : picked.length
    if (!n) return
    // Приёмка по всей выдаче берёт ровно тот набор, число которого показано на
    // кнопке: иначе «принять 310» и «принялось 280» разъезжаются в отчёте.
    const params = whole ? { ...queryParams(), verification_status: 'draft' } : {}
    const scope = whole ? `${n} черновых строк под фильтр «${filterNote()}»` : `${n} выбранных строк`
    if (!confirm(to === 'verified'
      ? `Принять ${scope}?\n\n«Проверено» останется и после следующего перегона, а условие и ответ прогон обновит как обычно.`
      : `Вернуть ${scope} в черновик? Приёмка с них снимется.`)) return
    setBusy(true)
    setNotice('')
    questionsAPI.bulkVerify(params,
                            whole ? { all_matching: true, verification_status: to }
                                  : { ids: picked, verification_status: to })
      .then(res => {
        load(page)
        loadProgress()
        loadPending()
        loadTransQueue()
        // после load(): он снимает старые сообщения, и написанный до него ответ
        // стирался бы, не дойдя до глаз
        setDone(res.data.changed
          ? `Статус «${to === 'verified' ? 'проверено' : 'черновик'}» у ${res.data.changed} строк.`
          : 'Ничего не изменилось: эти строки уже были в таком статусе.')
      })
      .catch(e => setNotice(errorText(e)))
      .finally(() => setBusy(false))
  }

  // модалка сама решает, закрыться ей (после сохранения) или остаться (после отката);
  // editing обновляем тем же ответом — иначе в окне остаётся устаревший паспорт
  const saved = (data) => {
    setRows(rs => rs.map(r => (r.id === data.id ? data : r)))
    setEditing(e => (e && e.id === data.id ? data : e))
    loadProgress()
    loadPending()
    loadTransQueue()
  }

  const sel = {
    height: 38, borderRadius: 10, border: '1px solid var(--border)', padding: '0 12px',
    fontSize: 13, background: '#fff', cursor: 'pointer', maxWidth: 260,
  }

  // Доска ответов печатается под последним условием темы, поэтому строки страницы
  // сгруппированы по темам: порядок выдачи (id) сам не знает, где блок кончается.
  // Одна тема на двух страницах выдачи даст свою доску на каждой — она собирает то,
  // что на этой странице видно, и честно об этом пишет числом строк.
  const byTopic = new Map()
  rows.forEach(q => {
    const k = q.topic_name || ''
    if (!byTopic.has(k)) byTopic.set(k, [])
    byTopic.get(k).push(q)
  })

  // Перевод знает оригинал по паспорту, оригинал — нет: бэкенд дописывает к строке
  // `translation_id`, иначе метка на русской карточке зависела бы от того, попал ли
  // её перевод в эту же страницу выдачи.
  // «↔ #34960» ведёт к паре: номер перевода = номер оригинала с хвостом «:kk», поэтому
  // поиска по оригинальному номеру хватает на обе строки. Фильтры языка, статуса и
  // «только переводы» разрезали бы пару, поэтому на переходе они снимаются.
  const showPair = (q) => {
    const base = String(q.external_id || '').replace(/:kk$/, '')
    if (!base) { setNotice('У этой строки нет печатного номера — перейти к паре нельзя'); return }
    setFilterLanguage('')
    setFilterStatus('')
    setFilterTranslated(false)
    setNeedle(base)
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
          <select value={filterDifficulty} onChange={e => setFilterDifficulty(e.target.value)} style={sel}>
            <option value="">Любая сложность</option>
            {DIFFICULTY.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
          </select>
          <select value={filterGrade} onChange={e => setFilterGrade(e.target.value)} style={sel}>
            {GRADE_FILTER.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
          </select>
          <select value={filterLanguage} onChange={e => setFilterLanguage(e.target.value)} style={sel}>
            {LANGUAGE.map(([v, n]) => <option key={v} value={v}>{v ? `Язык: ${n}` : n}</option>)}
          </select>
          <button className="btn btn-sm" onClick={toggleTranslated}
                  disabled={!transQueue && !filterTranslated}
                  title="Строки, у которых в паспорте есть исходник: их перевёл конвейер, глаз человека над ними ещё не был"
                  style={{ ...sel, border: filterTranslated ? '2px solid var(--primary)' : '1px solid var(--border)',
                           color: filterTranslated ? 'var(--primary)' : 'var(--text-secondary)',
                           background: filterTranslated ? 'rgba(99,102,241,0.08)' : '#fff' }}>
            Переводы на проверке{transQueue === null ? '…' : ` (${transQueue})`}
          </button>
          <select value={filterFormat} onChange={e => setFilterFormat(e.target.value)} style={sel}>
            {FORMAT.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
          </select>
          <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
            <Search size={13} strokeWidth={1.8} style={{ position: 'absolute', left: 10, color: 'var(--text-secondary)' }} />
            <input value={needle} onChange={e => setNeedle(e.target.value)} placeholder="Поиск: кусок условия, формулы или номер"
              style={{ ...sel, width: 280, paddingLeft: 28 }} />
          </span>
        </div>
        {notice && <div style={{ marginTop: 10, fontSize: 13, color: '#991B1B' }}>{notice}</div>}
      </div>

      {/* Пакетная приёмка: фильтруешь «черновики» и отмечаешь проверенными всю
          выдачу, вместо того чтобы заходить в окно редактуры на каждую задачу. */}
      <div className="card" style={{ padding: '10px 16px', marginBottom: 20, display: 'flex',
                                     gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>
          Пакетная приёмка
        </span>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
          выбрано {picked.length} · в выдаче {total} · черновиков под фильтр {pending === null ? '…' : pending} · {filterNote()}
        </span>
        <button className="btn btn-sm btn-outline" disabled={!rows.length}
                onClick={() => setPicked(picked.length ? [] : rows.map(r => r.id))}
                style={{ borderRadius: 10, padding: '4px 12px' }}>
          {picked.length ? 'Снять выбор' : `Выбрать ${rows.length} на странице`}
        </button>
        <button className="btn btn-sm btn-outline" disabled={!picked.length || busy}
                onClick={() => bulk('verified', false)}
                style={{ borderRadius: 10, padding: '4px 12px' }}>
          Принять выбранное{picked.length ? ` (${picked.length})` : ''}
        </button>
        <button className="btn btn-sm btn-outline" disabled={!picked.length || busy}
                onClick={() => bulk('draft', false)} title="Отменить приёмку"
                style={{ borderRadius: 10, padding: '4px 12px', color: '#991B1B' }}>
          В черновик
        </button>
        <button className="btn btn-sm btn-primary" disabled={!pending || busy}
                onClick={() => bulk('verified', true)}
                title="Отметить «проверено» все черновики, которые сейчас под фильтром"
                style={{ marginLeft: 'auto', borderRadius: 10, padding: '6px 14px' }}>
          {busy ? 'Принимаю…' : pending === null ? 'Считаю…' : pending
            ? `Принять все ${pending} черновиков под фильтр`
            : 'Принимать нечего: черновиков под фильтр нет'}
        </button>
        {done && <span style={{ fontSize: 13, color: '#065F46' }}>{done}</span>}
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>
          Всего: {total} · на странице {rows.length}
          {progress && (
            <button className="btn btn-sm btn-outline" onClick={() => setFilterStatus('draft')}
                    title="Остались только те, которые никто не смотрел глазами"
                    style={{ marginLeft: 10 }}>
              вычитано {progress.verified} из {progress.total} · недосмотрено {progress.total - progress.verified}
            </button>
          )}
        </div>
        {loading ? (
          <div className="text-center py-4"><div className="spinner"></div></div>
        ) : rows.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>
            <HelpCircle size={40} strokeWidth={1.5} style={{ opacity: 0.3, marginBottom: 12 }} />
            <p>Под этот фильтр оцифрованных задач нет.</p>
          </div>
        ) : rows.map((q, i) => {
          const pr = q.provenance || {}
          const card = (
            <div key={q.id} style={{ padding: '18px 20px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8, alignItems: 'center' }}>
                {/* выбор для пакетной приёмки — здесь же, где человек видит строку */}
                <input type="checkbox" checked={picked.includes(q.id)} title="Выбрать для пакетной приёмки"
                       onChange={e => setPicked(rs => e.target.checked ? [...rs, q.id] : rs.filter(i => i !== q.id))}
                       style={{ width: 16, height: 16, accentColor: 'var(--primary)', cursor: 'pointer', marginRight: 2 }} />
                <span style={chip('rgba(99,102,241,0.08)', 'var(--primary)')}>{q.subject_name}</span>
                {/* язык строки: перевод — отдельная строка банка, и без бейджа
                    казахское условие выглядело бы правкой русского на том же месте */}
                <span style={chip(q.language === 'kk' ? 'rgba(13,148,136,0.12)' : 'rgba(107,114,128,0.12)',
                                  q.language === 'kk' ? '#0F766E' : '#374151')}
                      title={q.language === 'kk' ? 'қазақша' : 'русский'}>
                  {(q.language || 'ru').toUpperCase()}
                </span>
                {(pr.translated_src_pk || q.translation_id) && (
                  <button className="btn btn-sm" onClick={() => showPair(q)}
                          title={pr.translated_src_pk
                            ? `Это перевод строки #${pr.translated_src_pk}`
                            : `Эту строку перевели: #${q.translation_id}`}
                          style={{ ...chip('rgba(99,102,241,0.08)', 'var(--primary)'),
                                   border: 'none', cursor: 'pointer' }}>
                    ↔ #{pr.translated_src_pk || q.translation_id}
                  </button>
                )}
                <span style={chip('rgba(16,185,129,0.08)', '#065F46')}>{q.topic_name}</span>
                <span style={chip('rgba(245,158,11,0.1)', '#92400E')}>
                  {/* у теста границей парсер считал слово «задача» — в чипе оно было бы ложью */}
                  {pr.format === 'тест' ? 'тест' : (pr.unit || 'задача')}{pr.page ? ` · с. ${pr.page}` : ''}
                </span>
                {pr.num && pr.format !== 'теория' && (
                  // номер, как его напечатал составитель: по нему строку ищут в
                  // развороте книги, и без него в банке остаётся только id строки.
                  // Рядом — буква уровня и сложность, которую из неё сделал импорт:
                  // сверка «B → Сложный» глазами иначе невозможна. У теоретического
                  // листа печатного номера нет (его граница — вся страница), поэтому
                  // чип «№» над ним был бы выдумкой.
                  <span style={chip('rgba(37,99,235,0.1)', '#1E40AF')}>
                    № {pr.num}
                    {pr.level ? ` · уровень ${pr.level} → ${(DIFFICULTY.find(([v]) => v === q.difficulty) || [, ''])[1]}` : ''}
                  </span>
                )}
                {q.grade && (
                  // класс решает тренер, книга его не печатает — значит на карточке
                  // он обязан быть виден, иначе фильтр «Класс» работает вслепую
                  <span style={chip('rgba(236,72,153,0.1)', '#9D174D')}>класс {q.grade}</span>
                )}
                <span style={chip(q.verification_status === 'verified' ? 'rgba(16,185,129,0.12)' : 'rgba(107,114,128,0.12)',
                                  q.verification_status === 'verified' ? '#065F46' : '#374151')}>
                  {(STATUS.find(([v]) => v === q.verification_status) || [, 'Черновик'])[1].toLowerCase()}
                </span>
                {pr.human_edited && (
                  <span style={chip('rgba(59,130,246,0.12)', '#1E40AF')}>правил человек</span>
                )}
                {pr.accepted_by && (
                  // принято пакетом — не «правил»: условие мог и не трогать никто.
                  // «автоматом» отдельным цветом: глаз человека на такой строке не был,
                  // и путать её с вычитанной нельзя
                  <span style={pr.accepted_mode === 'auto'
                                  ? chip('rgba(245,158,11,0.12)', '#92400E')
                                  : chip('rgba(16,185,129,0.12)', '#065F46')}>
                    {pr.accepted_mode === 'auto' ? 'принято автоматом' : 'принято'}
                  </span>
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
                <button className="btn btn-sm btn-outline" onClick={() => remove(q)} title="Удалить из банка"
                        style={{ borderRadius: 10, padding: '4px 10px', color: '#991B1B' }}>
                  <Trash2 size={12} strokeWidth={1.5} />
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
              {/* ответа под условием нет намеренно: в книге он в конце блока списком,
                  и здесь те же строки собирает доска под темой */}
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6 }}>
                {pr.run}{pr.model ? ` · ${pr.model}` : ''}{pr.src_sha256 ? ` · источник ${String(pr.src_sha256).slice(0, 8)}` : ''}
                {pr.edited_at ? ` · правка ${String(pr.edited_at).slice(0, 10)} (${pr.edited_by})` : ''}
                {pr.accepted_at ? ` · принято ${String(pr.accepted_at).slice(0, 10)} — ${pr.accepted_by}` : ''}
              </div>
            </div>
          )
          // доска печатается под последней строкой темы — как ответы блока в книге;
          // пока тема не кончилась, карточка идёт одна
          if (i !== rows.length - 1 && rows[i + 1].topic_name === q.topic_name) return card
          return [card, <AnswersBoard key={`otvety-${q.id}`} items={byTopic.get(q.topic_name || '')} />]
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

      {editing && <EditModal q={editing} subjects={subjects} onClose={() => setEditing(null)} onSaved={saved} />}
    </div>
  )
}
