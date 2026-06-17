import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { importAPI, subjectsAPI } from '../../api'

export default function ImportPage() {
  const [subjects, setSubjects] = useState([])
  const [selectedSubject, setSelectedSubject] = useState('')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    subjectsAPI.list().then(res => {
      setSubjects(res.data)
      if (res.data.length > 0) setSelectedSubject(res.data[0].id)
    })
  }, [])

  const handleDownloadTemplate = async () => {
    try {
      const res = await importAPI.template()
      // Создаём ссылку для скачивания
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', 'ent_questions_template.xlsx')
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch {
      setError('Не удалось скачать шаблон')
    }
  }

  const handleFileChange = (e) => {
    setFile(e.target.files[0])
    setResult(null)
    setError('')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!file) {
      setError('Выберите файл')
      return
    }
    if (!selectedSubject) {
      setError('Выберите предмет')
      return
    }

    setLoading(true)
    setError('')
    setResult(null)

    try {
      const res = await importAPI.upload(file, selectedSubject)
      setResult(res.data)
      setFile(null)
      // Сбрасываем input file
      e.target.reset()
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка импорта')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Импорт из Excel</h1>
        <p className="page-subtitle">Массовая загрузка вопросов из таблицы</p>
      </div>

      {/* Шаг 1: Скачать шаблон */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">Шаг 1. Скачайте шаблон</div>
        <p style={{ color: 'var(--text-secondary)', marginBottom: 16 }}>
          Заполните шаблон по инструкции во втором листе файла.
          Новые темы создаются автоматически.
        </p>
        <button className="btn btn-primary" onClick={handleDownloadTemplate}>
          📥 Скачать шаблон Excel
        </button>
      </div>

      {/* Шаг 2: Загрузить файл */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">Шаг 2. Загрузите заполненный файл</div>

        {error && <div className="alert alert-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Предмет *</label>
            <select
              className="form-select"
              value={selectedSubject}
              onChange={e => setSelectedSubject(e.target.value)}
              style={{ maxWidth: 300 }}
            >
              {subjects.map(s => (
                <option key={s.id} value={s.id}>{s.icon} {s.name}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Excel-файл (.xlsx) *</label>
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={handleFileChange}
              style={{
                padding: '12px',
                border: '2px dashed var(--border)',
                borderRadius: 8,
                width: '100%',
                background: 'var(--bg)',
              }}
            />
            {file && (
              <div style={{ marginTop: 8, fontSize: 14, color: 'var(--success)' }}>
                ✓ Выбран файл: <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} КБ)
              </div>
            )}
          </div>

          <button type="submit" className="btn btn-success" disabled={loading || !file}>
            {loading ? <><span className="spinner"></span> Импорт...</> : '🚀 Загрузить вопросы'}
          </button>
        </form>
      </div>

      {/* Результат импорта */}
      {result && (
        <div className="card">
          <div className="card-header">Результат импорта</div>

          <div className="alert alert-success" style={{ fontSize: 16, fontWeight: 600 }}>
            ✅ {result.message}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 16 }}>
            <div style={{
              padding: 24, borderRadius: 12,
              background: '#D1FAE5', textAlign: 'center',
            }}>
              <div style={{ fontSize: 40, fontWeight: 800, color: '#065F46' }}>{result.created}</div>
              <div style={{ color: '#065F46' }}>Вопросов добавлено</div>
            </div>
            <div style={{
              padding: 24, borderRadius: 12,
              background: result.errors_count > 0 ? '#FEE2E2' : '#F3F4F6',
              textAlign: 'center',
            }}>
              <div style={{
                fontSize: 40, fontWeight: 800,
                color: result.errors_count > 0 ? '#991B1B' : 'var(--text-secondary)',
              }}>
                {result.errors_count}
              </div>
              <div style={{ color: result.errors_count > 0 ? '#991B1B' : 'var(--text-secondary)' }}>
                Ошибок
              </div>
            </div>
          </div>

          {/* Список ошибок */}
          {result.errors && result.errors.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Детали ошибок:</h3>
              <div style={{
                background: '#FEF2F2',
                borderRadius: 8,
                padding: 16,
                maxHeight: 200,
                overflowY: 'auto',
                fontSize: 13,
              }}>
                {result.errors.map((err, i) => (
                  <div key={i} style={{ padding: '4px 0', color: '#991B1B' }}>
                    • {err}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ marginTop: 20 }}>
            <Link to="/teacher/questions" className="btn btn-primary">
              Перейти к списку вопросов →
            </Link>
          </div>
        </div>
      )}

      {/* Подсказка */}
      <div className="card" style={{ marginTop: 20, background: '#F0F9FF' }}>
        <div className="card-header">📋 Формат шаблона</div>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Тема</th>
                <th>Текст вопроса</th>
                <th>Сложность</th>
                <th>A</th>
                <th>B</th>
                <th>C</th>
                <th>D</th>
                <th>Правильный</th>
                <th>Объяснение</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Алгебра</td>
                <td>Чему равно 2+2?</td>
                <td>easy</td>
                <td>3</td>
                <td>4</td>
                <td>5</td>
                <td>6</td>
                <td><strong>B</strong></td>
                <td>2+2=4</td>
              </tr>
              <tr>
                <td>Геометрия</td>
                <td>Сумма углов треугольника?</td>
                <td>medium</td>
                <td>90°</td>
                <td>180°</td>
                <td>270°</td>
                <td>360°</td>
                <td><strong>B</strong></td>
                <td>Всегда 180°</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 12 }}>
          Сложность: <code>easy</code> / <code>medium</code> / <code>hard</code> (или по-русски: лёгкий/средний/сложный)
        </p>
      </div>
    </div>
  )
}
