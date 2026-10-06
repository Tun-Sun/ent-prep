# -*- coding: utf-8 -*-
"""Досчитывает деньги по уже записанным токенам: ставка пришла позже прогона.

    python pipeline/set_rate.py out_kasatkina_em --in 0.75 --out 3.00

Формула та же, что в ocr.Spend.money(): thinking-токены входят в исходящие,
прочитанный из кэша вход не платится. Никаких новых чисел не появляется —
только ставка и арифметика поверх usage.json.
"""
import argparse
import io
import json
import os


def money(d, p_in, p_out):
    return ((d["paid_in"] - d["cache_read"]) * p_in
            + (d["paid_out"] + d["paid_th"]) * p_out) / 1e6


def saved(d, p_in, p_out):
    return (d["saved_in"] * p_in + d["saved_out"] * p_out) / 1e6


ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--in", dest="p_in", type=float, required=True, help="за млн входных токенов")
ap.add_argument("--out", dest="p_out", type=float, required=True, help="за млн исходящих, thinking входит сюда")
a = ap.parse_args()

path = os.path.join(a.out, "usage.json")
u = json.load(io.open(path, encoding="utf-8"))
t = u.get("total") or {}
if not t:
    raise SystemExit(f"{path}: нет блока total — считать нечего")

u["price_per_mtok"] = {"in": a.p_in, "out": a.p_out,
                       "tier": "до 200k токенов контекста; thinking считается в исходящих"}
u["money"] = round(money(t, a.p_in, a.p_out), 4)
u["money_cache_saved"] = round(saved(t, a.p_in, a.p_out), 4)
u["money_total"] = u["money"]
pages = json.load(io.open(os.path.join(a.out, "run.json"), encoding="utf-8"))["render"]["pages"]
units = len(json.load(io.open(os.path.join(a.out, "tasks.json"), encoding="utf-8"))["tasks"])
print(f"{a.out}: {t['paid_in']} в / {t['paid_out']}+{t['paid_th']} из токенов, {t['attempts']} попыток API")
print(f"  деньги ${u['money']:.4f} за прогон = ${u['money'] / pages:.5f} за страницу "
      f"({pages} стр.) = ${u['money'] / units:.5f} за единицу банка ({units} шт.)")
print(f"  кэш съел {t['cache']} страниц и сэкономил ${u['money_cache_saved']:.4f}")
json.dump(u, io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"  записано в {path}")
