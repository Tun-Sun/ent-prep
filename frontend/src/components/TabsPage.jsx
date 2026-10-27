import { useSearchParams } from 'react-router-dom'

// Экран-обёртка с вкладками: несколько готовых страниц становятся одним разделом
// сайдбара. Сами страницы не переписаны — у каждой свои фильтры и свои переходы на
// редактирование, и старые маршруты продолжают работать.
//
// Вкладка живёт в параметре `?tab=`: ссылку на конкретную вкладку можно дать из
// другого места платформы, а переход назад по браузеру не сбрасывает человека на
// первую вкладку.
export default function TabsPage({ tabs }) {
  const [params, setParams] = useSearchParams()
  const asked = params.get('tab')
  const active = tabs.some(t => t.key === asked) ? asked : tabs[0].key
  const tab = tabs.find(t => t.key === active)

  return (
    <div>
      <div className="bank-tabs">
        {tabs.map(t => (
          <button key={t.key} type="button"
                  className={`bank-tab ${t.key === active ? 'is-active' : ''}`}
                  onClick={() => setParams(prev => {
                    // фильтр внутри экрана живёт в тех же параметрах: переключение
                    // вкладки не имеет права его стирать
                    const next = new URLSearchParams(prev)
                    next.set('tab', t.key)
                    return next
                  }, { replace: true })}>
            {t.label}
          </button>
        ))}
      </div>
      {tab.node}
    </div>
  )
}
