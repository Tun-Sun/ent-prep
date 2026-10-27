import TabsPage from '../../components/TabsPage'
import StudentsPage from './StudentsPage'
import GroupsPage from './GroupsPage'

// «Ученики и группы» (Блок 4): журнал и группы — один раздел сайдбара, две вкладки.
export default function TeacherStudentsSectionPage() {
  return (
    <TabsPage tabs={[
      { key: 'students', label: 'Ученики', node: <StudentsPage /> },
      { key: 'groups', label: 'Группы', node: <GroupsPage /> },
    ]} />
  )
}
