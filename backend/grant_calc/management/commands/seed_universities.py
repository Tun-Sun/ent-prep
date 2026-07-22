from django.core.management.base import BaseCommand
from grant_calc.models import University

UNIVERSITIES = [
    {"name": "КазНУ им. аль-Фараби", "city": "Алматы", "uni_type": "national", "icon": "🏛️", "min_score": 85, "specializations": "IT, экономика, право, медицина, инженерия", "info": "Топ-200 QS. Грант 2025: IT — 90, право — 90, физика — 70, химия — 80, мед — 119"},
    {"name": "КазНМУ им. Асфендиярова", "city": "Алматы", "uni_type": "medical", "icon": "🏥", "min_score": 113, "specializations": "Общая медицина, стоматология, фармация, педиатрия", "info": "Грант 2025: мед — 124, педиатрия — 113, фармация — 112, медпроф — 102"},
    {"name": "КазНПУ им. Абая", "city": "Алматы", "uni_type": "pedagogical", "icon": "🎓", "min_score": 90, "specializations": "Педагогика, психология, филология, история", "info": "Главный педвуз РК. Грант: 80–95 по спец."},
    {"name": "КазНИТУ им. Сатпаева", "city": "Алматы", "uni_type": "national", "icon": "⚙️", "min_score": 85, "specializations": "Инженерия, горное дело, нефтегаз, IT", "info": "Satbayev University. Грант: инж. — 80, IT — 90"},
    {"name": "КазУМОиМЯ им. Абылай хана", "city": "Алматы", "uni_type": "national", "icon": "🌍", "min_score": 100, "specializations": "Языки, перевод, международные отношения", "info": "Главный языковой вуз. Грант: перевод — 111"},
    {"name": "КазНАИУ", "city": "Алматы", "uni_type": "agro", "icon": "🌾", "min_score": 70, "specializations": "Агрономия, ветеринария, биотехнология, пищевые технологии", "info": "Ведущий аграрный вуз РК, осн. 1929"},
    {"name": "МУИТ", "city": "Алматы", "uni_type": "it", "icon": "💻", "min_score": 90, "specializations": "IT, кибербезопасность, Data Science, разработка ПО", "info": "Ведущий IT-вуз. Грант 2025: IT — 90, инфобез — 90, связь — 71"},
    {"name": "КБТУ", "city": "Алматы", "uni_type": "it", "icon": "💻", "min_score": 100, "specializations": "IT, инженерия, бизнес, нефтегаз", "info": "Грант 2025: IT — 110, финансы — 116, инж. — 76–86, горное — 75"},
    {"name": "СДУ им. Демиреля", "city": "Алматы", "uni_type": "it", "icon": "🌐", "min_score": 90, "specializations": "IT, право, экономика, инженерия", "info": "Обучение на англ. Высокий конкурс на грант"},
    {"name": "АУЭС", "city": "Алматы", "uni_type": "it", "icon": "⚡", "min_score": 80, "specializations": "Энергетика, IT, телекоммуникации", "info": "Ун-т энергетики и связи. Грант: 75–85"},
    {"name": "Нархоз", "city": "Алматы", "uni_type": "other", "icon": "💰", "min_score": 100, "specializations": "Экономика, право, IT, госуправление", "info": "Грант: IT — 105, экон — 103, аудит — 114"},
    {"name": "КазЖенПУ", "city": "Алматы", "uni_type": "pedagogical", "icon": "👩‍🎓", "min_score": 90, "specializations": "Педагогика, естествознание, языки", "info": "Нац. женский педуниверситет. Грант: 85–95"},
    {"name": "AlmaU", "city": "Алматы", "uni_type": "other", "icon": "📊", "min_score": 80, "specializations": "Бизнес, менеджмент, финансы, маркетинг", "info": "Алматы Менеджмент Университет"},
    {"name": "КазНАИ им. Жургенова", "city": "Алматы", "uni_type": "other", "icon": "🎨", "min_score": 75, "specializations": "Кино, театр, музыка, изо", "info": "Нац. академия искусств + творч. экзамен"},
    {"name": "Turan University", "city": "Алматы", "uni_type": "other", "icon": "📚", "min_score": 75, "specializations": "IT, экономика, журналистика, дизайн", "info": "Частный вуз с 1992 года"},
    {"name": "Caspian University", "city": "Алматы", "uni_type": "other", "icon": "📚", "min_score": 70, "specializations": "Юриспруденция, экономика, IT, менеджмент", "info": "Частный вуз с 1992 года"},
    {"name": "ЕНУ им. Гумилёва", "city": "Астана", "uni_type": "national", "icon": "🏛️", "min_score": 95, "specializations": "IT, экономика, право", "info": "Грант 2025: IT — 110, право — 96, физика — 95, химия — 95, финансы — 111"},
    {"name": "Назарбаев Университет", "city": "Астана", "uni_type": "national", "icon": "⭐", "min_score": 120, "specializations": "Все направления (отдельный конкурс)", "info": "Автономный вуз. На англ. Свой конкурс, не ЕНТ"},
    {"name": "Мед. университет Астана", "city": "Астана", "uni_type": "medical", "icon": "🏥", "min_score": 118, "specializations": "Медицина, общественное здоровье", "info": "Грант: мед — ~120, общ. здоровье — 115"},
    {"name": "КазАТУ им. Сейфуллина", "city": "Астана", "uni_type": "agro", "icon": "🌾", "min_score": 80, "specializations": "С/х, ветеринария, пищевые технологии", "info": "Аграрный вуз. Целевые гранты: 75–85"},
    {"name": "Astana IT University", "city": "Астана", "uni_type": "it", "icon": "💻", "min_score": 80, "specializations": "IT, Data Science, кибербез, ИИ", "info": "Грант 2025: IT — 80, инфобез — 85, связь — 70, электротех — 75"},
    {"name": "КАЗГЮУ им. Нарикбаева", "city": "Астана", "uni_type": "other", "icon": "⚖️", "min_score": 120, "specializations": "Право, международные отношения, экономика", "info": "Грант 2025: право — 125, финансы — 130, МО — 135, психология — 120"},
    {"name": "КазНУИ (Шабыт)", "city": "Астана", "uni_type": "national", "icon": "🎨", "min_score": 85, "specializations": "Музыка, театр, кино и ТВ, хореография", "info": "Ведущий творческий вуз Астаны + творч. экзамен"},
    {"name": "AIU (Astana International)", "city": "Астана", "uni_type": "other", "icon": "🎓", "min_score": 80, "specializations": "Образование, IT, бизнес, психология", "info": "Грант 2025: педагогика — 80, IT — 81, психология — 88, финансы — 99"},
    {"name": "Международный ун-т Астана", "city": "Астана", "uni_type": "other", "icon": "🏢", "min_score": 75, "specializations": "Бизнес, IT, право, лингвистика", "info": "Международные программы"},
    {"name": "Астана Медикал Университет", "city": "Астана", "uni_type": "medical", "icon": "🏥", "min_score": 110, "specializations": "Общая медицина, стоматология, фармация", "info": "Частный медвуз. Грант: мед — 110–120"},
    {"name": "ЮКУ им. Ауэзова", "city": "Шымкент", "uni_type": "national", "icon": "🏛️", "min_score": 80, "specializations": "Инженерия, педагогика, IT, экономика, медицина", "info": "Крупнейший по числу студентов вуз РК. Грант 2025: инж. — 65, архит. — 100, финансы — 127"},
    {"name": "ЮКМА", "city": "Шымкент", "uni_type": "medical", "icon": "🏥", "min_score": 110, "specializations": "Общая медицина, стоматология, фармация", "info": "Ведущий медвуз юга Казахстана"},
    {"name": "ЮКПУ им. Жанибекова", "city": "Шымкент", "uni_type": "pedagogical", "icon": "🎓", "min_score": 80, "specializations": "Педагогика, филология, математика, начальное образование", "info": "Один из старейших вузов юга РК"},
    {"name": "КарУ им. Букетова", "city": "Караганда", "uni_type": "national", "icon": "🏛️", "min_score": 85, "specializations": "Филология, IT, экономика, юриспруденция, педагогика", "info": "Нац. исследовательский ун-т центр. Казахстана"},
    {"name": "КарТУ им. Сагинова", "city": "Караганда", "uni_type": "technical", "icon": "⚙️", "min_score": 80, "specializations": "Горное дело, металлургия, машиностроение, IT", "info": "Ведущий технический вуз центр. РК"},
    {"name": "КГМУ", "city": "Караганда", "uni_type": "medical", "icon": "🏥", "min_score": 105, "specializations": "Общая медицина, стоматология, фармация, педиатрия", "info": "1-е место среди медвузов по THE Impact. Грант 2025: мед — 112, педиатрия — 105, фарм — 105"},
    {"name": "КЭУ Казпотребсоюза", "city": "Караганда", "uni_type": "other", "icon": "💰", "min_score": 70, "specializations": "Экономика, бизнес, финансы, IT, туризм", "info": "Частный экономический вуз, 60+ лет"},
    {"name": "АРУ им. Жубанова", "city": "Актобе", "uni_type": "national", "icon": "🏛️", "min_score": 80, "specializations": "Педагогика, филология, IT, экономика, юриспруденция", "info": "Многопрофильный региональный вуз"},
    {"name": "ЗапКазМедУ им. Оспанова", "city": "Актобе", "uni_type": "medical", "icon": "🏥", "min_score": 110, "specializations": "Общая медицина, стоматология, фармация", "info": "Единственный медвуз западного региона"},
    {"name": "Торайгыров университет", "city": "Павлодар", "uni_type": "national", "icon": "🏛️", "min_score": 75, "specializations": "Инженерия, педагогика, IT, экономика, энергетика", "info": "Крупнейший вуз Павлодарской обл. Грант 2025: IT — 101, финансы — 117, инж. — 50–63"},
    {"name": "ПавПедУ им. Маргулана", "city": "Павлодар", "uni_type": "pedagogical", "icon": "🎓", "min_score": 80, "specializations": "Педагогика, филология, начальное образование", "info": "Педагогический вуз Павлодара"},
    {"name": "КРУ им. Байтурсынулы", "city": "Костанай", "uni_type": "national", "icon": "🏛️", "min_score": 80, "specializations": "Педагогика, филология, IT, экономика, юриспруденция", "info": "Ведущий вуз Костанайской обл."},
    {"name": "КИнЭУ им. Дулатова", "city": "Костанай", "uni_type": "agro", "icon": "🌾", "min_score": 70, "specializations": "Агрономия, ветеринария, экономика, IT, инженерия", "info": "Аграрно-технический профиль"},
    {"name": "АтырГУ им. Досмухамедова", "city": "Атырау", "uni_type": "national", "icon": "🏛️", "min_score": 80, "specializations": "Педагогика, филология, экономика, юриспруденция", "info": "Ведущий вуз Атырауской обл."},
    {"name": "АУНГ им. Утебаева", "city": "Атырау", "uni_type": "technical", "icon": "🛢️", "min_score": 80, "specializations": "Нефтегазовое дело, геология, энергетика, экология", "info": "Единственный гос. нефтегазовый вуз РК"},
    {"name": "КасУТИ им. Есенова", "city": "Актау", "uni_type": "technical", "icon": "⚙️", "min_score": 80, "specializations": "Нефтегаз, морское дело, инженерия, IT", "info": "Ведущий технический вуз Мангистау"},
    {"name": "ТарРУ им. Дулати", "city": "Тараз", "uni_type": "national", "icon": "🏛️", "min_score": 80, "specializations": "Инженерия, педагогика, IT, экономика, строительство", "info": "Крупнейший вуз Жамбылской обл."},
    {"name": "Университет Шакарима", "city": "Семей", "uni_type": "national", "icon": "🏛️", "min_score": 80, "specializations": "Инженерия, педагогика, ветеринария, IT, экономика", "info": "Многопрофильный вуз, осн. 1995"},
    {"name": "МедУни Семей", "city": "Семей", "uni_type": "medical", "icon": "🏥", "min_score": 110, "specializations": "Общая медицина, педиатрия, стоматология, фармация", "info": "Лучший медвуз РК по нац. рейтингу. Грант: мед — 110–120"},
    {"name": "ВКТУ им. Серикбаева", "city": "Усть-Каменогорск", "uni_type": "technical", "icon": "⚙️", "min_score": 80, "specializations": "Энергетика, машиностроение, IT, металлургия", "info": "Ведущий технический вуз ВКО, 4★ QS"},
    {"name": "КызУ им. Коркыт Ата", "city": "Кызылорда", "uni_type": "national", "icon": "🏛️", "min_score": 80, "specializations": "Педагогика, IT, инженерия, экономика, филология", "info": "Ведущий вуз Кызылординской обл."},
    {"name": "СКГУ им. Козыбаева", "city": "Петропавловск", "uni_type": "national", "icon": "🏛️", "min_score": 80, "specializations": "Педагогика, инженерия, IT, экономика, юриспруденция", "info": "Ведущий вуз Северного Казахстана"},
    {"name": "ЗапКазУ им. Утемисова", "city": "Уральск", "uni_type": "national", "icon": "🏛️", "min_score": 80, "specializations": "Педагогика, филология, IT, экономика, юриспруденция", "info": "Крупнейший вуз ЗКО"},
    {"name": "МКТУ им. Ясави", "city": "Туркестан", "uni_type": "national", "icon": "🌐", "min_score": 85, "specializations": "Медицина, инженерия, педагогика, IT, теология", "info": "Первый международный вуз РК, 4 языка"},
    {"name": "КокУ им. Уалиханова", "city": "Кокшетау", "uni_type": "national", "icon": "🏛️", "min_score": 80, "specializations": "Педагогика, медицина, IT, экономика, юриспруденция", "info": "Ведущий вуз Акмолинской обл."},
    {"name": "ЖетГУ им. Жансугурова", "city": "Талдыкорган", "uni_type": "national", "icon": "🏛️", "min_score": 80, "specializations": "Педагогика, филология, IT, экономика, юриспруденция", "info": "Ведущий вуз Жетысуского региона"},
]


class Command(BaseCommand):
    help = 'Заполняет таблицу вузов с проходными баллами'

    def handle(self, *args, **options):
        created = 0
        for i, data in enumerate(UNIVERSITIES):
            _, was_created = University.objects.update_or_create(
                name=data['name'],
                city=data['city'],
                defaults={
                    'uni_type': data['uni_type'],
                    'icon': data['icon'],
                    'min_score': data['min_score'],
                    'specializations': data['specializations'],
                    'info': data.get('info', ''),
                    'sort_order': i,
                },
            )
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f'Добавлено {created} вузов. Всего: {University.objects.count()}'))
