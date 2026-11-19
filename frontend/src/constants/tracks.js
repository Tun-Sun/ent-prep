// Треки платформы: обычная школа (5–10), ЕНТ и NUET (11 класс).
// Один словарь на все экраны: подписи и правила показа не должны расходиться.
export const TRACK_LABELS = {
  school: 'Школа',
  ent: 'ЕНТ',
  nuet: 'NUET',
}

export const GRADUATION_TRACKS = [
  { value: 'ent', label: 'ЕНТ', hint: 'Подготовка к ЕНТ' },
  { value: 'nuet', label: 'NUET', hint: 'Подготовка к NUET' },
]

export const isStudent = (user) => user?.role === 'student'

/** Трек ученика; у тренера и админа его нет. */
export const trackOf = (user) => (isStudent(user) ? user?.track || '' : '')

/** Все треки ученика: основной и выданные учителем/админом. */
export const tracksOf = (user) => [
  ...(isStudent(user) && user?.track ? [user.track] : []),
  ...(Array.isArray(user?.extra_tracks) ? user.extra_tracks : []),
]

/** ЕНТ-инструменты (гранты, Rush, дуэли, симуляция) видят ЕНТ и тренеры. */
export const seesEntTools = (user) => !isStudent(user) || tracksOf(user).includes('ent')

/** 11-классник, который ещё не выбрал ЕНТ/NUET. */
export const needsTrack = (user) => isStudent(user) && Number(user?.grade) === 11 && !trackOf(user)

export const trackLabel = (track) => TRACK_LABELS[track] || 'не выбран'
