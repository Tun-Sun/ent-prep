import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { subjectsAPI } from '../../api'

export default function SubjectListPage() {
  const [subjects, setSubjects] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    subjectsAPI.list()
      .then(res => setSubjects(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center mt-8"><div className="spinner"></div></div>

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Предметы</h1>
        <p className="page-subtitle">Выберите предмет и начните тестирование</p>
      </div>

      <div className="subjects-grid">
        {subjects.map(subj => (
          <div key={subj.id} className="subject-card" onClick={() => navigate(`/test/start/${subj.id}`)}>
            <div className="subject-icon">{subj.icon}</div>
            <div className="subject-name">{subj.name}</div>
            <div className="subject-desc">{subj.description}</div>
            <div className="subject-stats">
              <div>
                <div className="subject-stat-value">{subj.topic_count}</div>
                <div className="subject-stat-label">Тем</div>
              </div>
              <div>
                <div className="subject-stat-value">{subj.question_count}</div>
                <div className="subject-stat-label">Вопросов</div>
              </div>
            </div>
            <button className="btn btn-primary mt-4" style={{ width: '100%' }}>
              Начать тест
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
