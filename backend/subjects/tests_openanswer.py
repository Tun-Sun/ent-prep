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
