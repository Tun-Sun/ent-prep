"""Нормализация текста для сверки: LaTeX и Юникод приводятся к одному виду."""
import re, unicodedata

ZWSP = "​"

SUP = {"¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
       "⁰": "0", "⁻": "-", "₁": "1", "₂": "2", "₃": "3"}

CMD = {"omega": "ω", "pi": "π", "tau": "τ", "alpha": "α", "beta": "β", "cdot": "·", "times": "x",
       "sqrt": "", "frac": "", "text": "", "mathrm": "", "operatorname": "", "gamma": "γ", "delta": "δ",
       "lambda": "λ", "mu": "μ", "nu": "ν", "rho": "ρ", "phi": "φ", "degree": "0"}


def norm(s):
    s = "".join(SUP.get(c, c) for c in s)
    s = unicodedata.normalize("NFKD", s)
    s = s.replace(ZWSP, "").replace("ё", "е")
    s = re.sub(r"\\(?:operatorname|text|mathrm)\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\([a-zA-Z]+)", lambda m: CMD.get(m.group(1), " "), s)
    s = re.sub(r"[{}_$^\\]", "", s)
    s = re.sub(r"[^\w\dωπταβγδλμνρφ·]", " ", s)
    # пробелы выбрасываем: переносы слов по строкам не должны считаться расхождением
    return re.sub(r"\s+", "", s).lower()
