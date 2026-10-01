import { useEffect, useRef } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

/**
 * FormattedText — безопасно рендерит текст с HTML и LaTeX формулами.
 *
 * Поддерживаемые форматы формул:
 *   \( ... \)        — инлайн формула
 *   $ ... $          — инлайн формула (если не конфликтует с долларами)
 *   $$ ... $$        — блочная формула (на отдельной строке)
 *   \[ ... \]        — блочная формула
 *
 * Пример: "Найдите \\(x^2 + 2x + 1\\) при x=3"
 *
 * Также рендерит базовый HTML (из парсеров/импорта).
 */
export default function FormattedText({ text, as: Tag = 'span', className = '', markdown = false, ...rest }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || !text) return
    // Рендерим KaTeX в готовый DOM, чтобы формулы стали красивыми
    const formulaEls = containerRef.current.querySelectorAll('.formula-inline, .formula-block')
    formulaEls.forEach(el => {
      const latex = el.getAttribute('data-latex') || ''
      const displayMode = el.classList.contains('formula-block')
      // KaTeX принимает один \tag на формулу, а модель ставит две нумерованные строки
      // через \qquad — иначе на экране красное «ParseError: Multiple \tag»
      const parts = (latex.match(/\\tag\{/g) || []).length > 1 ? latex.split(/\s*\\qquad\s*/) : [latex]
      try {
        el.innerHTML = ''
        parts.forEach(part => {
          const span = document.createElement('span')
          el.appendChild(span)
          katex.render(part.trim(), span, {
            displayMode,
            throwOnError: false,
          })
        })
      } catch {
        el.textContent = latex
      }
    })
  }, [text])

  if (!text) return null

  // Преобразуем исходный текст в HTML: выделяем формулы, экранируем опасное
  const html = formatText(text, markdown)

  return (
    <Tag
      ref={containerRef}
      className={`formatted-text ${className}`}
      dangerouslySetInnerHTML={{ __html: html }}
      {...rest}
    />
  )
}

/**
 * Основная функция обработки текста:
 * 1. Выделяем LaTeX-формулы в защитные плейсхолдеры
 * 2. Очищаем HTML от опасных тегов/атрибутов
 * 3. Возвращаем формулы как <span class="formula">
 */
function formatText(input, markdown = false) {
  if (!input) return ''

  let text = String(input)
  const formulas = []

  // 1. Сначала блочные формулы: $$...$$ и \[...\]
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (_, f) => {
    const idx = formulas.length
    formulas.push({ latex: f.trim(), block: true })
    return `\u0000FORMULA_${idx}\u0000`
  })
  text = text.replace(/\\\[([\s\S]+?)\\\]/g, (_, f) => {
    const idx = formulas.length
    formulas.push({ latex: f.trim(), block: true })
    return `\u0000FORMULA_${idx}\u0000`
  })

  // 2. Инлайн формулы: \(...\)
  text = text.replace(/\\\(([\s\S]+?)\\\)/g, (_, f) => {
    const idx = formulas.length
    formulas.push({ latex: f.trim(), block: false })
    return `\u0000FORMULA_${idx}\u0000`
  })

  // 3. Одиничные $...$ — инлайн формулы (осторожно, чтобы не задеть деньги)
  // Только если вокруг $ нет букв/цифр (чтобы не ломать "$5")
  text = text.replace(/(?<![a-zA-Z0-9])\$([^$\n]+?)\$(?![a-zA-Z0-9])/g, (_, f) => {
    const idx = formulas.length
    formulas.push({ latex: f.trim(), block: false })
    return `\u0000FORMULA_${idx}\u0000`
  })

  // 4. Оцифровка книги — markdown: ссылки на рисунки, *курсив*, таблицы |…| .
  // Без этого шага банк показывает сырой исходник посреди условия.
  if (markdown) text = renderMarkdown(text)

  // 5. Очищаем HTML от опасных тегов и атрибутов
  text = sanitizeHtml(text)

  // 6. Защищаем плейсхолдеры формул от sanitize
  // Заменяем их на span-ы с KaTeX
  text = text.replace(/\u0000FORMULA_(\d+)\u0000/g, (_, idx) => {
    const f = formulas[parseInt(idx)]
    if (!f) return ''
    const cls = f.block ? 'formula-block' : 'formula-inline'
    const escaped = escapeAttr(f.latex)
    return `<span class="${cls}" data-latex="${escaped}"></span>`
  })

  return text
}

/**
 * Подмножество markdown, которое реально встречается в оцифровке: картинки ![..](..),
 * *курсив* / **жирный**, таблицы из строк |…|. Заголовков и списков в единицах нет —
 * не добавляем то, что никто не производит.
 */
const FIGURE = /!\[([^\]]*)\]\(([^)]+)\)/g
const TABLE_ROW = /^\|[\s:|-]+\|$/

function renderMarkdown(text) {
  const out = []
  let rows = null
  const flush = () => {
    if (rows) out.push(`<table>${rows.join('')}</table>`)
    rows = null
  }
  for (const raw of text.split('\n')) {
    const ln = raw.trim()
    if (ln.startsWith('|')) {
      if (TABLE_ROW.test(ln)) continue
      const cells = ln.replace(/^\||\|$/g, '').split('|').map(c => `<td>${inlineMarkdown(c.trim())}</td>`)
      ;(rows = rows || []).push(`<tr>${cells.join('')}</tr>`)
      continue
    }
    flush()
    if (ln) out.push(inlineMarkdown(ln))
  }
  flush()
  return out.join('<br>')
}

function inlineMarkdown(s) {
  return s
    // путь assets/p04_fig1.png живёт в папке прогона, в браузере его нет: остаётся подпись
    .replace(FIGURE, (_, alt) => `<span class="figure-ref">${alt || 'рисунок'}</span>`)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
    // модель пишет «_Ответ:_» так же часто, как «*Ответ:*»; подчёркивания формул сюда
    // не доходят — они уже спрятаны в плейсхолдеры
    .replace(/_([^_\n]+)_/g, '<em>$1</em>')
}

// Убираем <script>, <iframe>, on* атрибуты, javascript: ссылки; теги вне списка молча
// вырезаются вместе с содержимым — сюда приходит текст из чужих сканов.
function sanitizeHtml(html) {
  // Эскейпим то, что выглядит как формулы-плейсхолдеры (чтобы не сломать их)
  // 1. Удаляем <script>, <iframe>, <object>, <embed> и их содержимое
  html = html.replace(/<\s*(script|iframe|object|embed|style|link|meta)[\s\S]*?<\/\s*\1\s*>/gi, '')
  // Самозакрывающиеся опасные теги
  html = html.replace(/<\s*(script|iframe|object|embed|style|link|meta)[^>]*?>/gi, '')

  // 2. Удаляем on* атрибуты (onclick, onload и т.д.)
  html = html.replace(/\s+on\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')

  // 3. Удаляем javascript: в href/src
  html = html.replace(/(href|src)\s*=\s*("javascript:[^"]*"|'javascript:[^']*')/gi, '$1="#"')

  // 4. Разрешаем только безопасные теги из нашего списка
  const allowed = ['p','br','b','strong','i','em','u','sub','sup','span','div',
                   'img','ul','ol','li','table','tr','td','th','tbody','thead',
                   'code','pre','blockquote','h1','h2','h3','h4','h5','h6']
  const allowedStr = allowed.join('|')
  // Удаляем теги, которых нет в списке
  html = html.replace(/<\s*(\/?)(\w+)([^>]*)>/g, (match, slash, tag, attrs) => {
    if (allowed.includes(tag.toLowerCase())) {
      return `<${slash}${tag}${attrs}>`
    }
    return '' // удаляем неизвестный тег
  })

  return html
}

function escapeAttr(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
