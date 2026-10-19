"""Разрез условия: разбор решения обязан уходить из `text` в `solution_latex`.

Проверяется то, из-за чего правка вообще затевалась: ученик видел ответ задачи
в её же условии. Поэтому три правила:

1. Разрезается только строка-маркер в начале строки (`| Дано:`, `Решение.`,
   `*Ответ:*`, в том числе внутри `$$…$$`) — слово «Дано» посреди условия права
   на разрез не даёт.
2. Условие не имеет права стать пустым: строка, где разбора больше, чем вопроса,
   выходит списком, а не пустой карточкой в банке.
3. Сухой прогон не трогает базу, `--apply` без `--decision` — отказ, а список
   old/new пишется в обоих режимах: им же и откатывать.
"""
from __future__ import annotations

import io
import json
import os
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from subjects.management.commands.split_solution_from_text import split_condition
from subjects.models import Question, Subject, Topic

LEAKED = ('Пылинка массой $m$ висит в однородном электрическом поле. Найти заряд $q$.\n'
          '| Дано: | Решение. Сила тяжести уравновешена силой поля |\n'
          '| :--- | :--- |\n'
          '| $mg$ | $$q = \\\\frac{mg}{E}$$ |\n'
          'Задача решена.\n'
          '*Ответ:* $q = 4{,}9\\cdot 10^{-18}$ КЛ.')


class SplitConditionTest(TestCase):
    """Что берёт правило разреза — и чего оно берёт намеренно."""

    def test_rezhet_tablicu_dano_i_otvet(self):
        cut = split_condition(LEAKED)
        self.assertIsNotNone(cut)
        index, condition, solution = cut
        self.assertEqual(condition, 'Пылинка массой $m$ висит в однородном электрическом поле. '
                                    'Найти заряд $q$.')
        self.assertTrue(solution.startswith('| Дано:'))
        self.assertIn('*Ответ:*', solution)
        self.assertGreater(index, 0)

    def test_otvet_v_kubke_latex_celym_blokom(self):
        """`$$Ответ: …$$` — строка ответа, напечатанная блочной формулой."""
        cut = split_condition('Какое время $t$ он будет двигаться до остановки?\n'
                              '$$ Ответ: t = 4 \\cdot 10^{-10}\\text{ с}. $$')
        self.assertEqual(cut[1], 'Какое время $t$ он будет двигаться до остановки?')
        self.assertTrue(cut[2].startswith('$$ Ответ:'))

    def test_ne_rezhet_slovo_v_seredine_usloviya(self):
        """«Дано» внутри вопроса — не разбор: разреза нет, строка не тронута."""
        self.assertIsNone(split_condition('В условии дано значение $E$, а что найдём — вопрос.'))

    def test_ne_rezhet_esli_usloviya_ne_ostalos(self):
        """Строка, где только разбор, не должна становиться пустым условием."""
        self.assertIsNone(split_condition('| Дано: | Решение. Всё, вопроса нет |\n*Ответ:* $x$'))


class SplitCommandTest(TestCase):
    """Команда: сухой прогон молчит в базу, `--apply` пишет и оставляет список."""

    @classmethod
    def setUpTestData(cls):
        subject = Subject.objects.create(name='Физика', slug='phys-split', icon='⚛️')
        cls.topic = Topic.objects.create(subject=subject, name='Электростатика')
        cls.leaked = cls.make('Касаткина. Электромагнетизм', LEAKED)
        cls.clean = cls.make('Касаткина. Электромагнетизм',
                             'Два шарика зарядили. Во сколько раз изменилась сила?')
        cls.half = cls.make('Сборник МКТ 6.1', 'Дано в середине: $p$ — давление. Найти объём.')

    @classmethod
    def make(cls, book, text):
        return Question.objects.create(topic=cls.topic, text=text, latex=text,
                                       latex_answer='', difficulty='easy',
                                       source_type='book_scan', question_type='open_answer',
                                       verification_status='verified', points=1,
                                       provenance={'book': book, 'page': 12, 'num': '5'})

    def out_file(self):
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        self.addCleanup(os.remove, path)
        return path

    def run_command(self, **opt):
        buf = io.StringIO()
        call_command('split_solution_from_text', stdout=buf, **opt)
        return buf.getvalue()

    def test_dry_ne_trogot_bazu(self):
        listing = self.out_file()
        out = self.run_command(out=listing, full='%d' % self.leaked.pk)
        self.leaked.refresh_from_db()
        self.assertIn('сухой прогон', out)
        self.assertIn('Дано:', self.leaked.text, 'условие осталось с разбором: база тронута')
        self.assertEqual(self.leaked.solution_latex, '')
        plan = json.load(open(listing, encoding='utf-8'))['plan']
        self.assertEqual([r['id'] for r in plan], [self.leaked.pk])
        self.assertNotIn('Дано', plan[0]['new_text'])
        self.assertIn('УЕХАЛО В solution_latex', out)

    def test_apply_perenosit_razbor_i_ostavlyayet_otkat(self):
        listing = self.out_file()
        self.run_command(apply=True, decision='решение владельца 19.10', out=listing)
        self.leaked.refresh_from_db()
        self.assertEqual(self.leaked.text,
                         'Пылинка массой $m$ висит в однородном электрическом поле. '
                         'Найти заряд $q$.')
        self.assertEqual(self.leaked.latex, self.leaked.text)
        self.assertIn('*Ответ:*', self.leaked.solution_latex)
        self.assertEqual(self.leaked.provenance['solution_split']['by'],
                         'решение владельца 19.10')
        # чистые строки не тронуты ни в text, ни в паспорте
        self.half.refresh_from_db()
        self.assertNotIn('solution_split', self.half.provenance)
        # откат читается из списка: old == то, что было
        rows = {r['id']: r for r in json.load(open(listing, encoding='utf-8'))['plan']}
        self.assertEqual(rows[self.leaked.pk]['old_text'], LEAKED)

    def test_apply_bez_decision_eto_otkaz(self):
        with self.assertRaises(CommandError):
            self.run_command(apply=True)

    def test_knigu_mozhno_ogranichit(self):
        listing = self.out_file()
        out = self.run_command(book='Сборник МКТ 6.1', out=listing)
        self.assertIn('строк с разбором в условии: 0', out)
