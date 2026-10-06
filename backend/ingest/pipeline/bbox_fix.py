#!/usr/bin/env python3
"""Определяет порядок координат в bbox, который вернула модель: [x0,y0,x1,y1] или [ymin,xmin,ymax,xmax].

Модель иногда переставляет (на скане стр.14 все 4 рамки перевёрнуты). Отличаем по структуре
вырезки: в полосе текста краска тянется поперёк почти каждой строки, у чертежа строки с краской
редкие. Решение принимаем мажоритетом по странице, а не по отдельной рамке.
"""
import io, json, os, sys
import numpy as np
from PIL import Image

FIG_MAX = 0.30      # доля «текстовых» строк ниже этого — чертёж
BLANK = 0.008       # меньше чернил — рамка промахнулась по пустому полю
SLICE_GAP = 0.45    # вдоль одной стороны пустых рядов больше половины — это просвет между строками
SLICE_INK = 0.98    # вдоль другой стороны пустых рядов меньше 2% — текст заполняет её целиком


def variants(bbox, W, H):
    a0, a1, a2, a3 = [float(v) / 1000 for v in bbox]
    return {"xy": (int(a0 * W), int(a1 * H), int(a2 * W), int(a3 * H)),
            "yx": (int(a1 * W), int(a0 * H), int(a3 * W), int(a2 * H))}


def to_xy(bbox, W, H, order):
    """bbox модели -> пиксельный прямоугольник (x0,y0,x1,y1) при выбранной расшифровке"""
    return variants(bbox, W, H)[order]


def textiness(sub, min_side=24):
    """0..1 — насколько вырезка похожа на текст; 2.0 — пустота (тоже брак)"""
    if min(sub.shape) < min_side:
        return None
    dark = sub < 128
    if float(dark.mean()) < BLANK:
        return 2.0
    f = dark.mean(axis=1)
    return float(((f > 0.12) & (f < 0.97)).mean())


def slice_like(sub, min_side=24):
    """True — вырезка это полоса сквозь колонку текста, а не чертёж.

    Узкая вертикальная полоса текста обманывает «текстовость»: в каждом её ряду только
    куски букв, доля краски ниже FIG_MAX, и детектор принимает её за чертёж. Отличает её
    то, что текст заполняет короткую сторону целиком (пустых колонок почти нет), а по длинной
    стороне ряды чередуются с межстрочными просветами. Чертеж так не умеет: вокруг него воздух.
    """
    if min(sub.shape) < min_side:
        return False
    dark = sub < 128
    gap = [float((dark.mean(axis=a) < 0.01).mean()) for a in (0, 1)]
    return max(gap) > SLICE_GAP and min(gap) < 1 - SLICE_INK


def score_page(gray, figures):
    """-> {'xy': [(текстовость, полоса_сквозь_текст)], 'yx': [...]}"""
    H, W = gray.shape
    sc = {"xy": [], "yx": []}
    for f in figures:
        b = f.get("bbox")
        if not b or len(b) != 4:
            continue
        for k, box in variants(b, W, H).items():
            x0, y0, x1, y1 = box
            sub = gray[max(0, y0):y1, max(0, x0):x1]
            sc[k].append((textiness(sub), slice_like(sub)))
    return sc


def orientation(gray, figures):
    """-> ('xy'|'yx', пояс)"""
    sc = score_page(gray, figures)
    fit = {k: sum(1 for t, s in v if t is not None and t < FIG_MAX and not s) for k, v in sc.items()}
    if fit["yx"] > fit["xy"]:
        return "yx", f"перевёрнуты ({fit['yx']} из {len(sc['yx'])} рамок)"
    return "xy", f"обычный порядок ({fit['xy']} из {len(sc['xy'])})"


def gray_of(png_bytes):
    im = Image.open(io.BytesIO(png_bytes)).convert("L")
    return np.asarray(im)


GUTTER = 25         # пустых рядов между полосой и чертежом, чтобы считать полосу чужой
LINE_MAX = 30       # высота одной строки текста при 300 dpi
BAND_MAX = 0.20     # полоса тоньше этой доли стороны — кандидат на отрез
SPAN_MIN = 0.40     # и тянется минимум на столько ширины — как строка условия


def _first_band(mask):
    """(длина первой полосы чернил у края, конец идущего за ней зазора) или None"""
    if not mask[0]:
        return None
    n, i = len(mask), 0
    while i < n and mask[i]:
        i += 1
    j = i
    while j < n and not mask[j]:
        j += 1
    if j - i < GUTTER or j >= n:
        return None
    return i, j


def trim_box(gray, box):
    """Сдвинуть границы рамки внутрь, отрезая у края строку текста, попавшую в bbox.

    Модель лепит в рамку соседнюю строку условия (на скане так вышло на стр. 14 и 16).
    Режем один раз на сторону и только по признакам одной строки: краска у самого края,
    полоса тонкая, за ней воздушный зазор, и тянется она поперёк. «Текстовость» для этого
    не годится — под неё попадают и горизонтальные рейки чертежа.
    """
    x0, y0, x1, y1 = box
    for edge in ("top", "bottom", "left", "right"):
        sub = gray[y0:y1, x0:x1]
        axis = 1 if edge in ("top", "bottom") else 0
        side = sub.shape[axis]
        dark = sub < 128
        m = dark.mean(axis=axis) > 0.002
        rev = edge in ("bottom", "right")
        if rev:
            m = m[::-1]
        b = _first_band(m)
        if not b:
            continue
        L, gap_end = b
        if L > min(BAND_MAX * side, LINE_MAX):
            continue
        # полоса тянется поперёк: для верха/низа считаем доли закрашенных столбцов,
        # для лева/права — строк
        cross = 0 if edge in ("top", "bottom") else 1
        band = dark[:L] if edge == "top" else dark[-L:] if edge == "bottom" \
            else dark[:, :L] if edge == "left" else dark[:, -L:]
        span = float((band.mean(axis=cross) > 0).mean())
        if span < SPAN_MIN:
            continue
        if edge == "top":
            y0 += gap_end
        elif edge == "bottom":
            y1 -= gap_end
        elif edge == "left":
            x0 += gap_end
        else:
            x1 -= gap_end
    return (x0, y0, x1, y1)


if __name__ == "__main__":
    import pymupdf
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = sys.argv[2] if len(sys.argv) > 2 else "out_v2"
    doc = pymupdf.open("C:/Ocifrovka/скан.pdf")
    for pf in sorted(os.listdir(os.path.join(ROOT, out, "pages"))):
        if not pf.endswith(".json"):
            continue
        d = json.load(io.open(os.path.join(ROOT, out, "pages", pf), encoding="utf-8"))
        figs = d.get("figures") or []
        if not figs:
            continue
        pm = doc[d["page"] - 1].get_pixmap(dpi=d.get("dpi", 300), colorspace=pymupdf.csGRAY)
        g = np.asarray(Image.frombytes("L", (pm.width, pm.height), pm.samples))
        pick, why = orientation(g, figs)
        sc = score_page(g, figs)
        print(f"стр{d['page']:>3} -> {pick}: {why}   " +
              " ".join(f"{t if t is not None else '-'}{'/ПОЛОСА' if s else ''}"
                       for t, s in sc["xy"]) + "  |  " +
              " ".join(f"{t if t is not None else '-'}{'/ПОЛОСА' if s else ''}"
                       for t, s in sc["yx"]))
