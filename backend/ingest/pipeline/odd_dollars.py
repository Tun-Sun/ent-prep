# -*- coding: utf-8 -*-
"""Где на экране останется голый `$`.

Парсер показа (`FormattedText`) сжимает инлайн-формулу правилом
`(?<![a-zA-Z0-9])$…$(?![a-zA-Z0-9])`: доллар, прижатый к цифре или букве,
границей не считается. Поэтому просто чётности долларов в строке верить
нельзя — надо сжимать строку ровно тем же правилом и смотреть, что осталось.
Оставшийся `$` опасен не сам: он склеивается с первым `$` дальше по строке,
и проза между ними уезжает в «формулу» — на экране каша без пробелов.

Смотрим все текстовые поля единицы: в tasks.json условие лежит в `markdown`,
а `latex` появляется только на импорте.
"""
import json
import re

RUNS = ["out_v2", "out_kasatkina_em", "out_b", "out_kz_1_6",
        "out_kz_5_2", "out_kz_6_4", "out_kz_yad"]

INLINE = re.compile(r"(?<![A-Za-z0-9])\$([^$\n]+?)\$(?![A-Za-z0-9])")
BARE = re.compile(r"(?<!\\)\$")

left = []
for run in RUNS:
    d = json.load(open(f"{run}/tasks.json", encoding="utf-8"))
    for t in d.get("tasks") or []:
        for field, val in t.items():
            vals = [val] if isinstance(val, str) else (
                [v for v in val if isinstance(v, str)] if isinstance(val, list) else [])
            for v in vals:
                for ln in v.split("\n"):
                    # два прохода, как в показе: сначала блочные $$…$$, потом инлайн
                    s = re.sub(r"(?<!\\)\$\$([\s\S]+?)\$\$", "", ln)
                    s = INLINE.sub("", s)
                    s = INLINE.sub("", s)
                    if BARE.search(s):
                        left.append((run, t.get("key") or t.get("num"), field,
                                     BARE.findall(s), ln[:120]))

print("строк, где на экране остаётся $:", len(left))
for r, k, f, n, ln in left:
    print(f"  {r} {k} [{f}] голых {len(n)}: {ln!r}")
