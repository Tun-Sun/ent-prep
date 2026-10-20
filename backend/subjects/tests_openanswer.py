"""Регрессия автопроверки внутри приложения: те же 49 случаев, что в лаборатории Шага 4.2.

Лабораторная папка на прод не едет, а перенесённый оттуда код без этих случаев
остался бы без охраны: правка в таблице единиц или в толерантности меняет вердикты
задач, которые ученики уже решают. Поэтому список переехал сюда без изменений —
он и есть контракт Level 1 + SymPy, замеренный на 588 ответах банка
(покрытие 96,3 % автоматом, конфликтов 0).
"""
from __future__ import annotations

from django.test import SimpleTestCase

from subjects.openanswer import compare, parts_hint, score_open_answer
from subjects.openanswer.cas import (_top_level_comma, decimal_comma_to_point,
                                     parse_by_latex_engine)
from subjects.openanswer.normalize import split_items, to_value

# эталон (как в банке), ответ ученика, ожидаемый вердикт, строгость по единицам
CASES = [
    (r'$\frac{\sqrt{2}}{2}$', r'1/\sqrt{2}', 'correct', False),
    (r'$\frac{\sqrt{2}}{2}$', r'\frac{1}{\sqrt{2}}', 'correct', False),
    (r'$-\frac{1}{\sqrt{3}}$', r'-1/sqrt(3)', 'correct', False),
    (r'$-42\frac{2}{3}$', '-42 2/3', 'correct', False),
    (r'$-42\frac{2}{3}$', '-42 1/3', 'incorrect', False),
    (r'$0,034$ м/с²', '0.034 м/с2', 'correct', False),
    (r'$s = 2\pi\Delta R = 2575\text{ км}$', '2575 км', 'correct', False),
    (r'$s = 2\pi\Delta R = 2575\text{ км}$', '2575000 м', 'correct', False),
    (r'$s = 2\pi\Delta R = 2575\text{ км}$', '2575', 'correct', False),
    (r'$s = 2\pi\Delta R = 2575\text{ км}$', '2575', 'pending_review', True),
    (r'$s = 2\pi\Delta R = 2575\text{ км}$', '2575 м', 'incorrect', False),
    (r'$1{,}8 \cdot 10^{3}$', '1800', 'correct', False),
    (r'$3{,}6 \cdot 10^{-4}\text{ м}$', '0,00036 м', 'correct', False),
    (r'$58\%$', '0,58', 'correct', False),
    (r'$\Delta\varphi = 2{,}5\text{ рад} = 144^\circ$', '144°', 'correct', False),
    (r'$144^\circ$', '2,51 рад', 'correct', False),
    (r'$2{,}4(09)$', '2,40909', 'correct', False),
    (r'$60\text{ об/мин}$', '1 об/с', 'correct', False),
    (r'$v = 4$ м/с', '5 м/с', 'incorrect', False),
    (r'а) $v = 465$ м/с; б) $v = 233$ м/с', '465 м/с', 'partial', False),
    (r'а) $v = 465$ м/с; б) $v = 233$ м/с', '465 м/с; 233 м/с', 'correct', False),
    (r'$V = CS$.', 'V=SC', 'correct', False),
    (r'$\frac{\pi R}{p}$.', 'pi*R/p', 'correct', False),
    (r'одноименно', 'одноимённо', 'pending_review', False),
    (r'докажите, что высоты пересекаются', 'пересекаются', 'pending_review', False),
    (r'$\frac{a^3}{6}$', 'a^3/5', 'incorrect', False),
    (r'$10$ см правее заряда $q_2$', '10 см', 'correct', False),
    (r'', 'что угодно', 'pending_review', False),
    (r'$5\sqrt{3}$', '5*1.73', 'correct', False),
    (r'$2$ м', '', 'incorrect', False),
    (r'$v = \frac{2\pi}{T}R \approx 10\text{ км/с}$', '10 км/с', 'correct', False),
    (r'$v = \frac{2\pi}{T}R \approx 10\text{ км/с}$', r'$\frac{2\pi R}{T}$', 'correct', False),
    (r'$10$ км/с', r'$\frac{2\pi R}{T} \approx 10$ км/с', 'correct', False),
    (r'$\frac{\sqrt[3]7+\sqrt[3]5}{12}$', r'(\sqrt[3]{7}+\sqrt[3]{5})/12', 'correct', False),
    (r'$-42\frac{2}{3}$', '-42,667', 'correct', False),
    (r'$-3$', '3', 'incorrect', False),
    (r'$1600$ кг/м ^3', '1,6 г/см3', 'correct', False),
    (r'$a \approx 4,5$ м/с²', '4.5 м/с^2', 'correct', False),
    (r'$24$ см ^3', '24 см^3', 'correct', False),
    (r'$24$ см ^3', '24', 'pending_review', True),
    (r'$24$ см ^3', '24 дм^3', 'incorrect', True),
    (r'$\frac{9\sqrt{2}}{8}$ см$^3$', r'9\sqrt{2}/8 см^3', 'correct', False),
    (r'$24\pi$ см³', '75,4 см^3', 'correct', False),
    (r'$24\pi$ см³', '24 см^3', 'incorrect', False),
    (r'$64\pi : 27$', '64*pi/27', 'correct', False),
    (r'$2d^3\sqrt2$', r'2\sqrt2', 'incorrect', False),
    (r'$2d^3\sqrt2$', r'2d^3\sqrt{2}', 'correct', False),
    (r'$2\pi R$', '2*pi*R', 'correct', False),
    (r'$4k\frac{qq_0}{\varepsilon a^2}$', r'\frac{4kqq_0}{\varepsilon a^2}', 'correct', False),
]


class SyntheticEquivalenceTest(SimpleTestCase):
    def test_every_case_keeps_its_verdict(self):
        for etalon, student, want, strict in CASES:
            with self.subTest(etalon=etalon[:38], student=student[:22], strict=strict):
                got = compare(etalon, student, strict_units=strict)
                self.assertEqual(got['verdict'], want, got['why'])

    def test_a_decided_verdict_says_which_road_decided_it(self):
        """`judged_by` — это не украшение: по нему видно, чем сверку решили, а где
        машина не решила и строка ушла человеку."""
        for etalon, student, want, strict in CASES:
            got = compare(etalon, student, strict_units=strict)
            if want == 'pending_review':
                continue
            self.assertIn(got['judged_by'], ('level1', 'cas'), (etalon, student))


class ScoreOpenAnswerEntryTest(SimpleTestCase):
    """Точка входа бэкенда: подсказка модели в базу не пишется, потому что модель уроку не вызывалась."""

    def test_model_suggestion_becomes_an_honest_empty_value(self):
        # словесная часть эталона — единственный случай, где compare помечает «спросить модель»
        res = compare('одноименно', 'одноимённо')
        self.assertEqual(res['verdict'], 'pending_review')
        self.assertEqual(res['judged_by'], 'model_suggestion')
        got = score_open_answer('одноименно', 'одноимённо')
        self.assertEqual(got['verdict'], 'pending_review')
        self.assertIsNone(got['judged_by'])

    def test_decided_verdicts_pass_through(self):
        self.assertEqual(score_open_answer(r'$2$ м', '2 м')['judged_by'], 'level1')
        self.assertEqual(score_open_answer(r'$2$ м', '')['verdict'], 'incorrect')


class ApprovedScoringRulesTest(SimpleTestCase):
    """Три правила, которые тренер утвердил 14.10, уже после переноса порта.

    В лабораторном фикстуре их не было, поэтому они под отдельным замком: порог
    округления, научная запись с `e` и судьба многочастного ответа со словесной
    частью. Правка в любом из трёх меняет вердикты живых задач.
    """

    def test_half_percent_relative_is_the_line(self):
        """0,5 % от значения: 18,09 ещё проходит, 18,1 — уже нет."""
        self.assertEqual(compare(r'$18$ см', '18,09 см')['verdict'], 'correct')
        self.assertEqual(compare(r'$18$ см', '18,1 см')['verdict'], 'incorrect')
        # атомный ответ: абсолютный пол его проглотил бы, поэтому порог относительный
        self.assertEqual(compare(r'$1{,}1 \cdot 10^{-10}$ Кл', '1,104e-10 Кл')['verdict'], 'correct')
        self.assertEqual(compare(r'$1{,}1 \cdot 10^{-10}$ Кл', '1,12e-10 Кл')['verdict'], 'incorrect')

    def test_a_word_answer_goes_to_the_human_instead_of_a_false_zero(self):
        """Словом вместо числа — машина не читала эту пару, и `incorrect` был бы ложным нулём."""
        got = compare(r'$\frac{a^3}{6}$', 'шесть делить на куб')
        self.assertEqual(got['verdict'], 'pending_review')
        self.assertEqual(got['parts'][0]['status'], 'student_text')
        self.assertIn('словом вместо числа', parts_hint(got['parts']))
        # но число, которое машина прочитала и отвергла, остаётся числом: слово рядом
        # не превращает честный `не совпало` в «проверьте глазами»
        got = compare('а) $18$ см; б) $5$ м/с', '18 см; 9 м/с; около пяти')
        self.assertEqual([p['status'] for p in got['parts']], ['matched', 'mismatched'])
        self.assertEqual(got['verdict'], 'partial')

    def test_scientific_notation_reads_every_way_the_keyboard_types_it(self):
        for student in ('1,1e-10', '1.1e-10', '1.1E-10', '1,1 · 10^-10', '1,1·10^(-10)'):
            got = compare(r'$1{,}1 \cdot 10^{-10}$ Кл', student)
            self.assertEqual(got['verdict'], 'correct', (student, got['why']))

    def test_a_bare_letter_after_the_number_is_still_a_unit_not_an_exponent(self):
        """`2 E` — напряжённость, `5 eV` — электрон-вольт: экспонента это только цифра сразу за знаком."""
        got = compare('2 E', '2 E')
        self.assertEqual(got['verdict'], 'correct')
        self.assertEqual(score_open_answer('2 E', '2')['verdict'], 'correct')

    def test_parts_say_which_subanswer_the_machine_matched(self):
        got = compare('а) $18$ см; б) вверх; в) $5$ м/с', 'а) 18 см; б) вниз; в) 9 м/с')
        self.assertEqual(got['verdict'], 'pending_review')
        self.assertEqual((got['matched'], got['total']), (1, 3))
        self.assertEqual([p['status'] for p in got['parts']],
                         ['matched', 'text', 'mismatched'])
        self.assertEqual(parts_hint(got['parts']),
                         'а): совпало, б): текст — проверьте глазами, в): не совпало')

    def test_unlabeled_parts_are_numbered_for_the_teacher(self):
        got = compare(r'$18$ см; $5$ м/с; вверх', '18 см; 6 м/с; вверх')
        self.assertEqual(got['verdict'], 'pending_review')
        self.assertEqual([p['part'] for p in got['parts']],
                         ['Часть 1', 'Часть 2', 'Часть 3'])
        self.assertIn('Часть 1: совпало', parts_hint(got['parts']))

    def test_single_part_pending_adds_no_hint(self):
        """Одна часть и так видна целиком: «Часть 1» вnotes — шум."""
        got = compare(r'$\frac{a^3}{6}$', 'шесть делить на куб')
        self.assertEqual(len(got['parts']), 1)
        self.assertEqual(got['verdict'], 'pending_review')


class DifferentSymbolsAreDifferentAnswersTest(SimpleTestCase):
    """Подстановка всем символам одного и того же числа равняла `A` и `B`.

    До правки `expressions_equal` проверяла структуру одним и тем же `7/10` для
    каждого имени: `2a == 2b`, `x^2 == y^2`, `a/b == b/a` — и машина ставила
    `correct` ответу, в котором ученик перепутал величину. Это ложные зачёты по
    всему банку формульных эталонов, поэтому случай заперт здесь, а не только в
    лаборатории: пара разных имён обязана оставаться `incorrect`.
    """

    def test_a_pair_of_different_names_never_matches(self):
        for etalon, student in (
                ('a', 'b'),
                ('2a', '2b'),
                (r'$x^2$', 'y^2'),
                (r'$\frac{a}{b}$', r'$\frac{b}{a}$'),
                (r'$v_A = 2$', r'$v_B = 2$'),
        ):
            with self.subTest(etalon=etalon, student=student):
                got = compare(etalon, student)
                self.assertEqual(got['verdict'], 'incorrect', got['why'])
                self.assertIn(got['judged_by'], ('level1', 'cas'))

    def test_the_same_answer_written_another_way_still_matches(self):
        """Обратная сторона: фикс не должен превратить честное равенство в ноль."""
        for etalon, student in (
                ('a', 'a'),
                ('2a', '2*a'),
                (r'$\frac{a^3}{6}$', 'a^3/6'),
                (r'$v_A = 2$', r'$v_A = 2$'),
                # индекс — часть имени: `v_A` против `v` сокращением не считается,
                # но и ученик обязан назвать ту же величину
                (r'$F_{\text{н}} = 5$', 'F = 5'),
                (r'$s = 2\pi\Delta R = 2575\text{ км}$', 's = 2575 км'),
        ):
            with self.subTest(etalon=etalon, student=student):
                got = compare(etalon, student)
                self.assertEqual(got['verdict'], 'correct', got['why'])

    def test_a_dropped_symbol_is_not_an_equivalence(self):
        """`2d^3√2` против `2√2`: буквы разные, и число из-за этого тоже."""
        self.assertEqual(compare(r'$2d^3\sqrt2$', r'$2\sqrt2$')['verdict'], 'incorrect')
        self.assertEqual(compare(r'$2d^3\sqrt2$', r'$2d^3\sqrt{2}$')['verdict'], 'correct')


class SingleChoiceLetterTest(SimpleTestCase):
    """Тест сверяется по литере варианта, а не через SymPy.

    Пока ключа в базе не было, эти строки шли к человеку; с ключом-буквой прежняя
    дорога попадала в CAS, где баг с подстановкой зачитывал любую букву любой.
    Литера — это Level 1: буква прочитана или нет, третьего исхода у теста нет.
    """

    def test_a_letter_option_is_read_through_every_way_the_keyboard_types_it(self):
        for etalon, forms in (
                ('A', ('A', 'a', 'А', 'а', '(A)', 'A)', 'а.', 'вариант A',
                       'А) ядролық күштер', 'А — ядролық күштер')),
                ('B', ('B', 'b', 'В', 'в', 'Б', 'б', '(в)', 'b.')),
                ('C', ('C', 'c', 'С', 'с', 'с.', 'вариант C')),
                ('D', ('D', 'd', '(d)', 'd.')),
                ('E', ('E', 'e', 'Е', 'е', 'E) 8,3 · 10^-26 кг')),
        ):
            for student in forms:
                with self.subTest(etalon=etalon, student=student):
                    got = score_open_answer(etalon, student, question_type='single_choice')
                    self.assertEqual(got['verdict'], 'correct', got['why'])
                    self.assertEqual(got['judged_by'], 'level1')

    def test_a_different_letter_is_a_real_zero_not_a_pending(self):
        for etalon, student in (('A', 'B'), ('A', 'б'), ('C', 'A'), ('E', 'в'),
                                ('B', 'D) 5 м/с')):
            with self.subTest(etalon=etalon, student=student):
                got = score_open_answer(etalon, student, question_type='single_choice')
                self.assertEqual(got['verdict'], 'incorrect', got['why'])
                self.assertEqual(got['judged_by'], 'level1')

    def test_an_answer_without_a_letter_still_goes_to_the_human(self):
        """Ученик переписал текст варианта без буквы — машина его не читает и ноль не ставит."""
        got = score_open_answer('A', 'ядролық күштер', question_type='single_choice')
        self.assertEqual(got['verdict'], 'pending_review')
        self.assertIsNone(got['judged_by'])
        self.assertEqual(got['parts'][0]['status'], 'undecided')
        # пустой ответ остаётся пустым ответом: литера тут ни при чём
        self.assertEqual(score_open_answer('A', '', question_type='single_choice')['verdict'],
                         'incorrect')

    def test_a_word_starting_with_a_option_letter_is_not_that_letter(self):
        """`Сутек` — это не вариант `C`, иначе первое слово ответа решало бы вердикт."""
        self.assertIsNone(score_open_answer('C', 'Сутек', question_type='single_choice')
                          ['judged_by'])
        self.assertEqual(score_open_answer('C', 'Сутек', question_type='single_choice')
                         ['verdict'], 'pending_review')

    def test_open_answer_rows_keep_their_number_pipeline(self):
        """Автодетект по букве не перетягивает на себя формульные и числовые ответы."""
        self.assertEqual(score_open_answer(r'$a \approx 4,5$ м/с²', r'$a \approx 4,5$ м/с²')
                         ['verdict'], 'correct')
        self.assertEqual(score_open_answer(r'$E = 400$ В', r'$E_k = 200$ В')['verdict'],
                         'incorrect')
        self.assertEqual(score_open_answer(r'$2$ м', '2 м')['verdict'], 'correct')

    def test_a_lone_letter_etalon_is_read_as_an_option_even_without_the_flag(self):
        """Ключ напечатан одной буквой, а тип задачи в банке ещё может быть открытым."""
        self.assertEqual(score_open_answer('B', 'б')['verdict'], 'correct')
        self.assertEqual(score_open_answer('B', 'с')['verdict'], 'incorrect')
        # но `$B = 50$ Тл` — формула, и буква из её начала ничего не решает
        self.assertEqual(score_open_answer(r'$B = 50$ Тл', r'$B = 50$ Тл')['verdict'], 'correct')


class OptionAlphabetUpToHTest(SimpleTestCase):
    """Блок ЕНТ с восемью вариантами: `F`, `G`, `H` читаются наравне с `A..E`.

    Задачи №16–20 листа «Ядролық физика» напечатаны с вариантами `A..H`, где `H`
    в скане стоит кириллической `Н`. Без этой литеры ученик физически не мог сдать
    верный вариант — машина объявляла его ответ нечитаемым.
    """

    def test_the_last_three_letters_are_read_in_any_layout(self):
        for etalon, forms in (
                ('F', ('F', 'f', '(F)', 'F)', 'F) α-бөлшек', 'вариант f')),
                ('G', ('G', 'g', 'g.', '(G)', 'G) 2 жыл')),
                ('H', ('H', 'h', 'Н', 'н', 'Н)', '(Н)', 'Н) жалпы массаның 1/8 бөлігі қалады')),
        ):
            for student in forms:
                with self.subTest(etalon=etalon, student=student):
                    got = score_open_answer(etalon, student, question_type='single_choice')
                    self.assertEqual(got['verdict'], 'correct', got['why'])
                    self.assertEqual(got['judged_by'], 'level1')

    def test_a_letter_past_E_is_a_real_zero_when_it_is_the_wrong_one(self):
        for etalon, student in (('F', 'G'), ('H', 'н, g'), ('G', 'f'), ('H', 'B')):
            with self.subTest(etalon=etalon, student=student):
                got = score_open_answer(etalon, student, question_type='single_choice')
                self.assertEqual(got['verdict'], 'incorrect', got['why'])


class MultipleOptionLettersTest(SimpleTestCase):
    """Многосоставный ключ: засчитывается ровно тот набор литер, что в эталоне.

    В блоке №16–20 правильных ответов от одного до трёх. Порядок, регистр, раскладка
    и слитный ввод вердикт менять не вправе, а лишняя или пропущенная литера — это
    неверный ответ, а не «половина»: частичного балла в ЕНТ нет.
    """

    def test_the_same_set_of_letters_is_read_through_every_spelling(self):
        for student in ('B, G', 'B,G', 'BG', 'G, B', 'G B', 'в, g', 'G. B.',
                        'B) 12·10^16; G) 2 жыл', 'B) 12·10^16, G) 2 жыл',
                        'вариант B, G', '(B) (G)'):
            with self.subTest(student=student):
                got = score_open_answer('B, G', student, question_type='single_choice')
                self.assertEqual(got['verdict'], 'correct', got['why'])
                self.assertEqual(got['judged_by'], 'level1')

    def test_three_letters_written_solid_equal_three_letters_with_commas(self):
        for student in ('BDH', 'B, D, H', 'н, b, d', 'H D B', 'B;D;H'):
            with self.subTest(student=student):
                self.assertEqual(score_open_answer('B, D, H', student,
                                                   question_type='single_choice')['verdict'],
                                 'correct')

    def test_a_partial_or_extra_set_is_a_real_zero(self):
        for etalon, student in (
                ('B, G', 'B'), ('B, G', 'G'), ('B, G', 'B, G, H'),
                ('B, D, H', 'B, D'), ('A, B, C', 'A, B, D'),
                ('D, F, G', 'D, F, H')):
            with self.subTest(etalon=etalon, student=student):
                got = score_open_answer(etalon, student, question_type='single_choice')
                self.assertEqual(got['verdict'], 'incorrect', got['why'])
                self.assertEqual(got['judged_by'], 'level1')

    def test_a_multi_letter_key_never_leaks_into_the_students_note(self):
        got = score_open_answer('B, G', 'B', question_type='single_choice')
        self.assertNotIn('G', got['why'])
        self.assertNotIn('B', got['why'])

    def test_an_unreadable_answer_under_a_multi_letter_key_calls_the_human(self):
        for student in ('ядролық күштер', '12', '12·10^16'):
            with self.subTest(student=student):
                got = score_open_answer('B, G', student, question_type='single_choice')
                self.assertEqual(got['verdict'], 'pending_review', got['why'])
                self.assertIsNone(got['judged_by'])

    def test_a_multi_letter_key_stays_a_key_and_not_a_formula(self):
        """`B, G` — две литеры, а не два слагаемых: в CAS эта строка не идёт."""
        got = score_open_answer('B, G', 'B, G', question_type='single_choice')
        self.assertEqual(got['judged_by'], 'level1')
        # набор литер читает только тест: одна верная литера из двух — неверный ответ
        self.assertEqual(score_open_answer('B, G', 'B', question_type='single_choice')['verdict'],
                         'incorrect')


class CommaStopsTheLatexRoadTest(SimpleTestCase):
    """П.2: `parse_latex('B, G')` молча режет хвост и возвращает `B`.

    Из-за этого в открытом ответе пара `B, G` против `B, G, H` давала ложное
    `correct`: сверялись левые токены. Дорога LaTeX теперь такие строки не берёт
    вовсе, и вердикт остаётся человеку.
    """

    def test_a_top_level_comma_refuses_the_latex_road(self):
        self.assertIsNone(parse_by_latex_engine('B, G'))
        self.assertIsNone(parse_by_latex_engine(r'2\pi R, 4\pi R'))

    def test_a_decimal_comma_is_not_mistaken_for_a_list(self):
        """Страж смотрит на строку после перевода запятой в точку: `1,5` — это число."""
        self.assertFalse(_top_level_comma(decimal_comma_to_point('1,5')))
        self.assertFalse(_top_level_comma(r'f\left(x, 1\right)'))
        self.assertTrue(_top_level_comma(decimal_comma_to_point('B, G')))
        self.assertTrue(parse_by_latex_engine('B, G') is None)

    def test_a_longer_list_is_not_credited_by_the_left_token(self):
        for etalon, student in (('B, G', 'B, G, H'), ('a, b', 'a, b, c'), ('B, G', 'B, G')):
            got = score_open_answer(etalon, student)
            self.assertNotEqual(got['verdict'], 'correct', '%s || %s' % (etalon, student))
            self.assertIsNone(got['judged_by'], 'вердикт не машины')


class RatioChainTest(SimpleTestCase):
    """П.3: цепочка отношений — то, что SymPy не решает, а в банке встречается.

    Три боевые строки (`34812`, `34817`, `34888`) сверяются попарными частными:
    пропорциональный ряд — тот же ответ, оборванный или неверный — не зачитывается.
    """

    def test_three_rows_of_the_book_match_themselves(self):
        for raw in (r'$3 : 2 : 1$.',
                    r'$S_{1} : S_{2} = \pi : 2;\quad V_{1} : V_{2} = \pi\sqrt{3} : 2$.',
                    r'$\frac{1}{a} : \frac{1}{b} : \frac{1}{c}$.'):
            got = score_open_answer(raw, raw)
            self.assertEqual(got['verdict'], 'correct', raw)
            self.assertEqual(got['judged_by'], 'cas', raw)

    def test_a_proportional_row_is_the_same_answer(self):
        self.assertEqual(score_open_answer(r'$3 : 2 : 1$.', '6 : 4 : 2')['verdict'], 'correct')
        self.assertEqual(score_open_answer(r'$3 : 2 : 1$.', '3:2:1')['verdict'], 'correct')
        self.assertEqual(score_open_answer(r'$3 : 2 : 1$.', '1,5 : 1 : 0,5')['verdict'], 'correct')

    def test_a_row_of_another_length_is_a_real_zero(self):
        for answer in ('3 : 2', '3 : 2 : 5', '2 : 4 : 8'):
            got = score_open_answer(r'$3 : 2 : 1$.', answer)
            self.assertEqual(got['verdict'], 'incorrect', answer)
            self.assertEqual(got['judged_by'], 'level1', answer)

    def test_inverse_reciprocals_are_the_same_chain(self):
        """`1/a : 1/b : 1/c` умножен на `abc` — это `bc : ac : ab`, тот же ответ."""
        etalon = r'$\frac{1}{a} : \frac{1}{b} : \frac{1}{c}$.'
        self.assertEqual(score_open_answer(etalon, 'bc : ac : ab')['verdict'], 'correct')
        self.assertEqual(score_open_answer(etalon, '1/a : 1/b : 1/c')['verdict'], 'correct')
        self.assertEqual(score_open_answer(etalon, 'a : b : c')['verdict'], 'incorrect')

    def test_two_named_parts_are_graded_one_by_one(self):
        etalon = r'$S_{1} : S_{2} = \pi : 2;\quad V_{1} : V_{2} = \pi\sqrt{3} : 2$.'
        self.assertEqual(score_open_answer(etalon, r'$S_{1} : S_{2} = 2\pi : 4; V_{1} : V_{2} = 2\pi\sqrt{3} : 4$.')
                         ['verdict'], 'correct')
        # ученик мог не переписывать имена величин — пустое имя слева не конфликт
        self.assertEqual(score_open_answer(etalon, r'\pi : 2; \pi\sqrt{3} : 2')['verdict'],
                         'correct')
        half = score_open_answer(etalon, r'$S_{1} : S_{2} = \pi : 3; V_{1} : V_{2} = \pi\sqrt{3} : 2$.')
        self.assertEqual(half['verdict'], 'partial')
        self.assertEqual([p['status'] for p in half['parts']], ['mismatched', 'matched'])
        # переставленные местами части — это ответ про другие величины
        self.assertEqual(score_open_answer(
            etalon, r'$V_{1} : V_{2} = \pi : 2; S_{1} : S_{2} = \pi\sqrt{3} : 2$.')['verdict'],
            'incorrect')

    def test_a_chain_against_prose_stays_with_the_teacher(self):
        got = score_open_answer(r'$3 : 2 : 1$.', 'в три раза больше')
        self.assertEqual(got['verdict'], 'pending_review')
        self.assertIsNone(got['judged_by'])


class BookTypographyStillParsesTest(SimpleTestCase):
    """П.3: три книжные записи, на которых парсер спотыкался сам о себя.

    Скобки при команде, единица, набранная дробью, и подпись в подстрочном индексе —
    всё это набор книги, а не ошибка ученика. Ни один из случаев не должен давать
    ложного вердикта: где машина не уверена, она зовёт человека.
    """

    def test_braces_after_a_command_are_not_stripped_off_the_command(self):
        """`\\sqrt{N}` без скобок превращался в `\\sqrtN` и переставал читаться."""
        self.assertEqual(score_open_answer(r'$\sqrt{N}$', r'$\sqrt{N}$')['verdict'], 'correct')
        self.assertEqual(score_open_answer(r'$\sqrt{N}$', 'sqrt(N)')['verdict'], 'correct')
        self.assertEqual(score_open_answer(r'$\sqrt{N}$', r'$\sqrt{2N}$')['verdict'], 'incorrect')
        self.assertEqual(score_open_answer(r'$\frac{q}{\pi\sigma}$', r'$\frac{q}{2\pi\sigma}$')
                         ['verdict'], 'incorrect')
        # дробь без скобок (`\frac16`) книга печатает и так — читается с обеих сторон
        self.assertEqual(score_open_answer(r'$\frac16$', r'$\frac16$')['verdict'], 'correct')
        self.assertEqual(score_open_answer(r'$\frac16$', r'$\frac18$')['verdict'], 'incorrect')

    def test_a_unit_written_as_a_fraction_is_a_unit_not_a_formula(self):
        """`\frac{Н}{Кл}` — это `Н/Кл`; как формула она в CAS не читается."""
        etalon = r'$E = 1{,}6\cdot 10^{4}\ \frac{\text{Н}}{\text{Кл}}$'
        self.assertEqual(to_value(split_items(etalon)[0]['text'])['kind'], 'number')
        self.assertEqual(score_open_answer(etalon, etalon)['verdict'], 'correct')
        self.assertEqual(score_open_answer(etalon, r'$1{,}6\cdot 10^{4}$ Н/Кл')['verdict'],
                         'correct')
        self.assertEqual(score_open_answer(etalon, '16000 Н/Кл')['verdict'], 'correct')
        self.assertEqual(score_open_answer(etalon, r'$1{,}6\cdot 10^{4}$ В')['verdict'],
                         'incorrect')

    def test_a_subscript_label_is_part_of_the_name_not_running_text(self):
        """`T_{\text{сут}}` — это имя величины; строка из-за неё не считается рассказом."""
        etalon = r'$v = \frac{2\pi(R_{\text{з}} + h)}{T_{\text{сут}}}$'
        self.assertEqual(to_value(split_items(etalon)[0]['text'])['kind'], 'expr')
        # но прочитать кириллицу в индексе CAS не может, поэтому ложного вердикта нет
        self.assertEqual(score_open_answer(etalon, etalon)['verdict'], 'pending_review')
        # а число с подписанной величиной остаётся числом: метку машины не ищет
        self.assertEqual(score_open_answer(r'$F = 5$ Н', r'$F_{\text{н}} = 5$ Н')['verdict'],
                         'correct')
