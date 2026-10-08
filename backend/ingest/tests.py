# -*- coding: utf-8 -*-
"""Оцифровка книги платформой: запуск прогона, его счётчики и путь в банк."""
import json
import shutil
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from subjects.models import Question, Subject
from users.models import User

from . import runner
from .models import STATUS_DONE, STATUS_FAILED, STATUS_RUNNING, IngestRun, folder_name


class FolderNameTest(TestCase):
    def test_cyrillic_and_spaces_survive_as_one_token(self):
        """Имя папки — он же префикс external_id: «Касаткина ЭМ.pdf» и «Касаткина
        ЭМ (2).pdf» не должны столкнуться в один прогон."""
        a = folder_name('Касаткина ЭМ.pdf')
        b = folder_name('Касаткина ЭМ (2).pdf')
        self.assertTrue(a.startswith('касаткина_эм_'))
        self.assertNotEqual(a, b)
        self.assertNotIn(' ', a)

    def test_unnamed_scan_still_gets_a_folder(self):
        self.assertTrue(folder_name('....pdf').startswith('book_'))


class RunApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.physics = Subject.objects.create(name='Физика', slug='physics', icon='⚡')
        cls.teacher = User.objects.create_user(username='t1', password='x', role='teacher')
        cls.student = User.objects.create_user(username='s1', password='x', role='student')

    def setUp(self):
        from unittest import mock

        self.tmp = tempfile.mkdtemp()
        self.patch = override_settings(INGEST_RUNS_DIR=self.tmp)
        self.patch.enable()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.spawned = []
        self.mock = mock.patch('ingest.api.runner.spawn', side_effect=lambda rid: self.spawned.append(rid))
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.client = APIClient()
        self.client.force_authenticate(user=self.teacher)

    def post(self, **fields):
        from django.core.files.uploadedfile import SimpleUploadedFile

        f = {'pdf': SimpleUploadedFile('кадров.pdf', b'%PDF-1.4 fake', 'application/pdf')}
        f.update(fields)
        return self.client.post('/api/ingest/runs/', f, format='multipart')

    def test_upload_starts_a_run_and_keeps_the_pdf_out_of_media(self):
        r = self.post(subject='physics', language='ru', book='Криволинейное движение')
        self.assertEqual(r.status_code, 201, r.content)
        run = IngestRun.objects.get()
        self.assertEqual(r.json()['name'], run.name)
        self.assertEqual(self.spawned, [run.pk])
        self.assertEqual(run.book, 'Криволинейное движение')
        pdf = Path(run.pdf_path)
        # Источник книги — не картинка вопроса: в media он отдавался бы наружу
        self.assertTrue(pdf.is_file())
        self.assertEqual(pdf.read_bytes(), b'%PDF-1.4 fake')
        self.assertEqual(pdf.parent, Path(self.tmp) / run.name)

    def test_not_a_pdf_is_refused(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        r = self.post(pdf=SimpleUploadedFile('скан.docx', b'word', 'application/msword'))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(IngestRun.objects.count(), 0)

    def test_book_label_is_required(self):
        """Без метки книги темы двух книг с одним разделом слились бы в одну."""
        r = self.post(subject='physics', language='ru')
        self.assertEqual(r.status_code, 400)

    def test_unknown_subject_and_language_are_refused(self):
        self.assertEqual(self.post(subject='magic', language='ru', book='x').status_code, 400)
        self.assertEqual(self.post(subject='physics', language='zz', book='x').status_code, 400)

    def test_second_run_waits_while_the_first_is_running(self):
        """Два прогона сразу — двойной счёт по API, и второй клик от нетерпения
        не должен запускать ту же книгу дважды."""
        IngestRun.objects.create(name='идёт', subject=self.physics, book='B', status=STATUS_RUNNING)
        r = self.post(subject='physics', language='ru', book='Касаткина')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.spawned, [])

    def test_student_cannot_digitalize_books(self):
        self.client.force_authenticate(user=self.student)
        self.assertEqual(self.post(subject='physics', language='ru', book='B').status_code, 403)


class StepsTest(TestCase):
    @override_settings(INGEST_RUNS_DIR='/tmp/runs', GEMINI_KEY_FILE='/etc/entprep/gemini.key',
                       INGEST_PRICE_IN=10.0, INGEST_PRICE_OUT=60.0)
    def test_every_step_gets_absolute_paths_and_the_key_file(self):
        """Ключ передаётся путём к файлу: в аргументах процесса он был бы виден
        в `ps`, а строка банка не должна зависеть от того, какая папка текущая."""
        steps = dict(runner.steps('книга_1', '/tmp/runs/книга_1/source.pdf'))
        ocr = steps['распознавание']
        self.assertIn('--key-file', ocr)
        self.assertEqual(ocr[ocr.index('--key-file') + 1], '/etc/entprep/gemini.key')
        self.assertEqual(Path(ocr[ocr.index('--out') + 1]), Path('/tmp/runs') / 'книга_1')
        self.assertEqual(ocr[ocr.index('--price-in') + 1], '10.0')
        self.assertNotIn('topdf.py', json.dumps(steps, ensure_ascii=False))


def unit(num='1', **over):
    base = {'key': f'Раздел#Задача{num}', 'num': num, 'word': 'Задача', 'kind': 'word',
            'scope': 'Раздел', 'block': 'Раздел', 'pages': [8],
            'spans': [{'page': 8, 'l0': 3, 'l1': 12}], 'figures': [], 'markdown': '$x = 1$',
            'answer_in': [], 'uncertain': [], 'options': 0, 'options_cyr': None,
            'options_list': []}
    base.update(over)
    return base


class RunBookIngestCommandTest(TestCase):
    """Команда прогона: счётчики берутся из файлов прогона, а не из воздуха,
    и в банк доезжает ровно то, что разобрал парсер."""

    @classmethod
    def setUpTestData(cls):
        cls.physics = Subject.objects.create(name='Физика', slug='physics', icon='⚡')

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # файл ключа подставляем настоящий: команда проверяет, что он на диске есть
        self.patch = override_settings(INGEST_RUNS_DIR=self.tmp, GEMINI_KEY_FILE=__file__)
        self.patch.enable()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        out = runner.run_dir('книга')
        (out / 'pages').mkdir(parents=True)
        (out / 'source.pdf').write_bytes(b'%PDF')
        self.out = out
        self.run = IngestRun.objects.create(name='книга', pdf_path=str(out / 'source.pdf'),
                                            subject=self.physics, language='ru', book='Книга')

    def fake_steps(self, ok=True, price=(10.0, 60.0), money=3.5, source_pages=None,
                   pages=('p08', 'p09')):
        from unittest import mock

        def run(argv, **kw):
            class R:
                returncode = 0 if ok else 1
            if 'ocr.py' in argv[1]:
                for n in pages:
                    (self.out / 'pages' / f'{n}.json').write_text('{"page": 8}', encoding='utf-8')
                json.dump({'price_per_mtok': {'in': price[0], 'out': price[1]}, 'money_total': money},
                          (self.out / 'usage.json').open('w', encoding='utf-8'))
            if 'index.py' in argv[1] and source_pages is not None:
                # сколько страниц в источнике — считает index.py, а не распознавание
                json.dump([{'page': p} for p in source_pages],
                          (self.out / 'index.json').open('w', encoding='utf-8'))
            if 'tasks.py' in argv[1]:
                json.dump({'run': 'книга', 'pages': len(pages),
                           'tasks': [unit(str(i + 1)) for i in range(len(pages))],
                           'answers': [], 'other': []},
                          (self.out / 'tasks.json').open('w', encoding='utf-8'))
            return R()

        return mock.patch('ingest.management.commands.run_book_ingest.subprocess.run', side_effect=run)

    def test_finished_run_counts_pages_units_money_and_lands_drafts(self):
        with self.fake_steps():
            call_command('run_book_ingest', self.run.pk)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, STATUS_DONE, self.run.error)
        self.assertEqual((self.run.pages, self.run.units, self.run.money), (2, 2, 3.5))
        self.assertIn('книга: создано 2', self.run.report)
        q = Question.objects.get(external_id='книга:p8:Задача1:Раздел')
        # Черновиком: прогон никто не вычитывал, а «проверено» ставит только человек
        self.assertEqual(q.verification_status, 'draft')
        self.assertEqual(q.topic.name, 'Книга · Раздел')

    def test_failed_step_leaves_the_bank_untouched(self):
        with self.fake_steps(ok=False):
            with self.assertRaises(SystemExit):
                call_command('run_book_ingest', self.run.pk)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, STATUS_FAILED)
        self.assertIn('распознавание', self.run.error)
        self.assertEqual(Question.objects.count(), 0)

    def test_no_rate_means_no_money(self):
        """Без ставки в отчёте пустота, а не ноль: «потрачено 0» звучит как
        бесплатная книга, хотя токены считались."""
        with self.fake_steps(price=(0, 0), money=0):
            call_command('run_book_ingest', self.run.pk)
        self.run.refresh_from_db()
        self.assertIsNone(self.run.money)

    def test_hole_in_the_book_is_named_but_the_run_still_lands(self):
        """Фильтр отбил страницу навсегда: статус остаётся «готово» — остальное в
        банке всё равно надо вычитывать, — но дырявая книга обязана быть названа."""
        with self.fake_steps(source_pages=(8, 9, 10)):
            call_command('run_book_ingest', self.run.pk)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, STATUS_DONE, self.run.error)
        self.assertIn('с.10', self.run.error)
        self.assertEqual(Question.objects.count(), 2)

    def test_book_without_a_single_page_fails_instead_of_importing_nothing(self):
        with self.fake_steps(source_pages=(8, 9), pages=()):
            with self.assertRaises(SystemExit):
                call_command('run_book_ingest', self.run.pk)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, STATUS_FAILED)
        self.assertIn('ни одной страницы', self.run.error)
        self.assertEqual(Question.objects.count(), 0)

    def test_run_without_key_dies_before_the_first_call(self):
        """Без ключа прогон не начнётся: иначе страница молча отвалится на первом
        же вызове, а тренер увидит «упало» без причины."""
        with override_settings(GEMINI_KEY_FILE=''):
            with self.assertRaises(SystemExit):
                call_command('run_book_ingest', self.run.pk)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, STATUS_FAILED)
        self.assertIn('GEMINI_KEY_FILE', self.run.error)


class FilterRefusalTest(TestCase):
    """Отказ safety-фильтра модели — это HTTP 200 без текста, и он случайен:
    на проде одна и та же страница отбилась один раз и три раза подряд прошла.
    Значит отказ надо перевызывать, а не считать ответом страницы."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent / 'pipeline'))
        import ocr
        cls.ocr = ocr

    def test_empty_parts_count_as_refusal(self):
        f = self.ocr.filter_refused
        self.assertTrue(f({}))
        self.assertTrue(f({'candidates': []}))
        self.assertTrue(f({'candidates': [{'content': {}}]}))
        self.assertTrue(f({'candidates': [{'content': {'parts': []}}]}))

    def test_answer_with_text_is_not_refusal(self):
        self.assertFalse(self.ocr.filter_refused(
            {'candidates': [{'content': {'parts': [{'text': 'Задача 1'}]}}]}))

    def test_reason_is_named_for_the_log(self):
        self.assertEqual(self.ocr.finish_reason({'candidates': [{'finishReason': 'RECITATION'}]}),
                         'RECITATION')
        self.assertEqual(self.ocr.finish_reason({'candidates': []}), 'пустой ответ')


class AnswersBlockOnTheSamePageTest(TestCase):
    """Ответы печатают и блоком в конце той же страницы, а не отдельным разворотом.
    Живой прогон платформы показал: такая строка прилипала к последней задаче страницы —
    в банк уходило условие со списком чужих ответов и пустым полем ответа."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import sys
        sys.path.insert(0, str(Path(__file__).parent / 'pipeline'))
        import tasks
        cls.tasks = tasks

    def parse(self, markdown):
        t = self.tasks
        pages = [{'page': 1, 'markdown': markdown}]
        units, answers, other, acc = t.walk(pages)
        for u in units:
            t.entities(u, {1: pages[0]})
        t.share_figures(units, {1: pages[0]})
        t.attach(units, answers, acc)
        return {u['num']: u for u in units}, acc

    def test_answers_block_becomes_answers_not_the_last_task(self):
        md = ('# Глава 1\n\n'
              'Задача 1.1. Два заряда по 2 нКл на расстоянии 10 см. Найдите силу.\n\n'
              'Задача 1.2. На каком расстоянии сила будет 0,225 Н?\n\n'
              '**Ответы к главе 1: 1.1) 5,4 мкН. 1.2) 100 см.**\n')
        got, acc = self.parse(md)
        self.assertEqual(got['1.1']['answer'], '5,4 мкН.')
        self.assertEqual(got['1.2']['answer'], '100 см.')
        self.assertNotIn('Ответы', got['1.2']['markdown'])
        # полный учёт знаков: новая ветка не имеет права ни потерять, ни удвоить строку
        self.assertEqual(sum(acc.values()), len(md) + 1)

    def test_exponent_inside_an_answer_is_not_a_new_record(self):
        got, _ = self.parse(
            '# Глава 1\n\n'
            'Задача 1.3. Пылинка массой 2 мкг покоится в поле 50 кВ/м. Найдите заряд.\n\n'
            '**Ответы к главе 1: 1.3) $4 \\cdot 10^{-13}$ Кл.**\n')
        self.assertEqual(got['1.3']['answer'], '$4 \\cdot 10^{-13}$ Кл.')

    def test_prose_about_answers_stays_where_it_was(self):
        """«Ответы на вопросы приведены в конце книги» — это условие задачи: без
        маркера записей ветка молчит и ничего не срезает."""
        got, _ = self.parse(
            '# Глава 1\n\n'
            'Задача 1.4. Точечный заряд 8 нКл. Найдите напряжённость в точке A.\n\n'
            'Ответы на вопросы 5–12 приведены в конце книги.\n')
        self.assertIn('Ответы на вопросы', got['1.4']['markdown'])


class NumberingRestartByBlockTest(TestCase):
    """Сборник с переразбивкой (Рустюмова): счёт номеров свой внутри каждого «БЛОК N»,
    блоки идут под одним §-заголовком, а ответы блока печатают списком или таблицей под
    заголовком «ОТВЕТЫ» после его вариантов А и В.

    Живой прогон 8 страниц лег без этой правки: из ~90 задач в банк ушли 38, остальные
    43 условия свернулись «ответами» задач первого блока, и у 23 задач в поле ответа
    стояло чужое условие."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import sys
        sys.path.insert(0, str(Path(__file__).parent / 'pipeline'))
        import tasks
        cls.tasks = tasks

    def parse(self, *markdown):
        t = self.tasks
        pages = [{'page': n + 1, 'markdown': md} for n, md in enumerate(markdown)]
        by_page = {p['page']: p for p in pages}
        units, answers, other, acc = t.walk(pages)
        for u in units:
            t.entities(u, by_page)
        t.share_figures(units, by_page)
        t.attach(units, answers, acc)
        return {(u['run'], u['num']): u for u in units}, acc

    def test_same_number_in_two_blocks_stays_two_tasks(self):
        got, _ = self.parse(
            '# ГЛАВА I\n\n## §1. СТЕПЕНИ\n\n'
            '**БЛОК 1. Вычислите:**\n\n### A\n\n'
            '**1)** $3{,}7 - 1{,}2$\n\n'
            '**2)** $5{,}4 : 0{,}6$\n',
            '**БЛОК 2. Сократите дробь:**\n\n**А**\n\n'
            '**1)** $\\frac{41^2 - 17^2}{37^2 - 21^2}$\n\n'
            '### ОТВЕТЫ:\n\n'
            '| 1) 1 | 2) 9 |\n')
        self.assertEqual(len(got), 3)                      # 1 и 2 блока 1, 1 блока 2
        self.assertEqual(got[(u'ГЛАВА I / БЛОК 2. Сократите дробь:', '1')]['answer'], '1')
        self.assertEqual(got[(u'ГЛАВА I / БЛОК 1. Вычислите:', '1')]['markdown'].strip(),
                         '$3{,}7 - 1{,}2$')

    def test_answers_table_without_a_number_header_is_read(self):
        """| 1) 1 | 2) 9 | — шапки «№» нет, веткой TABLE такая строка не бралась,
        и весь список ответов уезжал в «вне задач»."""
        got, _ = self.parse(
            '# ГЛАВА I\n\n**БЛОК 1. Вычислите:**\n\n'
            '**1)** $2{,}5 \\cdot 4$\n\n**2)** $9 - 0{,}7$\n\n'
            '### **ОТВЕТЫ:**\n\n'
            '| 1) 10 | 2) 8,3 |\n')
        self.assertEqual(got[(u'ГЛАВА I / БЛОК 1. Вычислите:', '1')]['answer'], '10')
        self.assertEqual(got[(u'ГЛАВА I / БЛОК 1. Вычислите:', '2')]['answer'], '8,3')

    def test_one_answers_list_covers_both_variants(self):
        """Ответы блока — одним списком на варианты А и В, и номер варианта для поиска
        ответа не годится: связывает их счёт (путь заголовков без буквы и без «ОТВЕТЫ»)."""
        got, _ = self.parse(
            '# ГЛАВА I\n\n**БЛОК 3. Сократите дробь:**\n\n**А**\n\n'
            '**1)** $\\frac{7^8}{49^2}$\n\n'
            '### В\n\n**2)** $\\frac{\\sqrt{12}}{\\sqrt{3}}$\n\n'
            '### ОТВЕТЫ:\n\n'
            '1) 350\n\n2) 2\n')
        run = u'ГЛАВА I / БЛОК 3. Сократите дробь:'
        self.assertEqual(got[(run, '1')]['answer'], '350')
        self.assertEqual(got[(run, '2')]['answer'], '2')

    def test_topic_is_the_block_not_the_variant_letter(self):
        """Тема строки в банке строится по области: «Книга · A» — это три темы на одну,
        различить которые потом нельзя."""
        got, _ = self.parse(
            '# ГЛАВА I\n\n**БЛОК 4. Освободитесь от иррациональности:**\n\n'
            '#### **A**\n\n**1)** $\\frac{4}{3-\\sqrt{3}}$\n\n'
            '### ОТВЕТЫ:\n\n1) $\\frac{6+2\\sqrt{3}}{3}$\n')
        u = got[(u'ГЛАВА I / БЛОК 4. Освободитесь от иррациональности:', '1')]
        self.assertEqual(u['scope'], 'БЛОК 4. Освободитесь от иррациональности:')
        self.assertEqual(u['answer'], '$\\frac{6+2\\sqrt{3}}{3}$')

    def test_prose_about_a_block_is_not_a_heading(self):
        """«Блок задач 1–5 решите письменно» внутри условия счёт не перебивает:
        заголовком считается только решётка или жирная строка, закрытая звёздочками."""
        got, _ = self.parse(
            '# ГЛАВА I\n\n**БЛОК 1. Вычислите:**\n\n'
            '**1)** Найдите сумму. Блок задач 1–5 решите письменно.\n\n'
            '**2)** $5 - 1{,}4$\n')
        self.assertEqual(len(got), 2)
        self.assertIn('Блок задач', got[(u'ГЛАВА I / БЛОК 1. Вычислите:', '1')]['markdown'])

    def test_balance_of_signs_survives_the_new_branches(self):
        md = ('# ГЛАВА I\n\n## §1. ДРОБИ\n\n**БЛОК 1. Вычислите:**\n\n**A**\n\n'
              '**1)** $2{,}5 + 1$ \n\n**2)** $7 : 2$\n\n'
              '### ОТВЕТЫ:\n\n| 1) 3,5 | 2) 3,5 |\n')
        _, acc = self.parse(md)
        self.assertEqual(sum(acc.values()), len(md) + 1)


class PrintedLevelLetterTest(TestCase):
    """Буква напечатанного уровня — своё поле единицы, а не часть темы и не счёт.

    В сборниках ЕНТ под «A» дают базовый уровень, под «B» — повышенный; по этой букве
    банк потом собирает задачи по сложности. В живом прогоне Рустюмовой уровни стоят
    внутри одного блока и по-разному набраны: жирной строкой без решётки («**B**») и
    решёткой («### В»), а модель на 300 dpi пишет одну и ту же букву то латиницей,
    то кириллическим гомоглифом. Без этого поля сложность книги в банк не доезжала."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent / 'pipeline'))
        import tasks
        cls.tasks = tasks

    def parse(self, *markdown):
        t = self.tasks
        pages = [{'page': n + 1, 'markdown': md} for n, md in enumerate(markdown)]
        by_page = {p['page']: p for p in pages}
        units, answers, other, acc = t.walk(pages)
        for u in units:
            t.entities(u, by_page)
        t.share_figures(units, by_page)
        t.attach(units, answers, acc)
        return {u['num']: u for u in units}, acc

    def test_bold_letter_without_hash_is_a_level(self):
        """«**B**» без решётки — сосед буквы «### B»: иначе строка ушла бы в тело
        предыдущей задачи, и повышенный уровень начался бы с её условия."""
        got, _ = self.parse(
            '# ГЛАВА I\n\n**БЛОК 2. Найдите значение выражения:**\n\n**А**\n\n'
            '**1)** $2{,}5 \\cdot 4$\n\n'
            '**B**\n\n**2)** $\\frac{4}{3-\\sqrt{3}}$\n\n'
            '### ОТВЕТЫ:\n\n| 1) 10 | 2) 4,6 |\n')
        self.assertEqual(got['1']['level'], 'A')
        self.assertEqual(got['2']['level'], 'B')
        # уровень не разрывает блок: тема (scope) и счётный путь (run) у обоих
        # уровней одного блока остаются общими — по ним ищется ответ блока
        self.assertEqual(got['2']['scope'], got['1']['scope'])
        self.assertEqual(got['2']['run'], got['1']['run'])
        self.assertEqual(got['1']['scope'], 'БЛОК 2. Найдите значение выражения:')
        self.assertEqual(got['2']['answer'], '4,6')

    def test_homoglyph_and_hash_forms_fold_into_one_letter(self):
        """Кириллическая «В» и латинская «B» — одна буква одного уровня: без свёртки
        одна страница дала бы два разных уровня и сложность разъехалась бы по строчке."""
        got, _ = self.parse(
            '# ГЛАВА I\n\n**БЛОК 1. Вычислите:**\n\n### В\n\n'
            '**1)** $5{,}4 : 0{,}6$\n\n**А**\n\n**2)** $3{,}7 - 1{,}2$\n\n'
            '### ОТВЕТЫ:\n\n1) 9\n\n2) 2,5\n')
        self.assertEqual(got['1']['level'], 'B')
        self.assertEqual(got['2']['level'], 'A')

    def test_task_above_any_letter_has_no_level(self):
        """Книга без уровней (Касаткина, теория): поле пустое, а не угаданное —
        иначе импорт поставил бы сложность там, где её никто не печатал."""
        got, _ = self.parse(
            '# ГЛАВА I\n\n## §1. СТЕПЕНИ\n\n**1)** $2^{5}$\n')
        self.assertEqual(got['1']['level'], '')

    def test_letters_across_pages_keep_the_block_numbering(self):
        """Буква уровня на новой странице не перебивает счёт: блок нумерует задачи
        сквозной лесенкой 1..30, и «B» посередине — ступень, а не новый раздел."""
        got, _ = self.parse(
            '# ГЛАВА I\n\n**БЛОК 1. Вычислите:**\n\n**A**\n\n'
            '**1)** $2 + 2$\n\n**2)** $3 + 3$\n',
            '**B**\n\n**3)** $4 + 4$\n\n'
            '### ОТВЕТЫ:\n\n1) 4\n\n2) 6\n\n3) 8\n')
        self.assertEqual(sorted(got), ['1', '2', '3'])
        self.assertEqual([got[n]['level'] for n in ('1', '2', '3')], ['A', 'A', 'B'])
        self.assertEqual(got['3']['answer'], '8')

    def test_balance_of_signs_survives_the_level_branch(self):
        md = ('# ГЛАВА I\n\n**БЛОК 1. Вычислите:**\n\n**A**\n\n**1)** $2{,}5 + 1$\n\n'
              '### В\n\n**2)** $7 : 2$\n\n### ОТВЕТЫ:\n\n| 1) 3,5 | 2) 3,5 |\n')
        _, acc = self.parse(md)
        self.assertEqual(sum(acc.values()), len(md) + 1)


class MissingPagesTest(TestCase):
    """Прогон обязан сам сказать, что книга легла в банк с дыркой."""
    def test_pages_absent_from_the_source_are_listed(self):
        from .management.commands.run_book_ingest import missing_pages

        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        (d / 'pages').mkdir()
        (d / 'pages' / 'p08.json').write_text('{}', encoding='utf-8')
        (d / 'pages' / 'p09.json').write_text('{}', encoding='utf-8')
        json.dump([{'page': 8}, {'page': 9}, {'page': 10}],
                  (d / 'index.json').open('w', encoding='utf-8'))
        self.assertEqual(missing_pages(str(d)), [10])

    def test_no_index_means_no_claims(self):
        """Без index.json утверждать нечего: выдумать список пропавших страниц
        хуже, чем промолчать."""
        from .management.commands.run_book_ingest import missing_pages

        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        self.assertEqual(missing_pages(str(d)), [])
