import TabsPage from '../../components/TabsPage'
import QuestionsPage from './QuestionsPage'
import AuthorialTestsPage from './AuthorialTestsPage'
import GoogleFormsImportPage from './GoogleFormsImportPage'

// «Все вопросы и тесты ЕНТ» (Блок 4): три экрана, которые раньше стояли в сайдбаре
// отдельными пунктами, — один раздел с вкладками.
export default function TeacherBankPage() {
  return (
    <TabsPage tabs={[
      { key: 'questions', label: 'Вопросы', node: <QuestionsPage /> },
      { key: 'authorial', label: 'Авторские тесты', node: <AuthorialTestsPage /> },
      { key: 'import', label: 'Импорт', node: <GoogleFormsImportPage /> },
    ]} />
  )
}
