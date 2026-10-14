"""Единицы измерения: таблица пересчёта в СИ и разбор хвоста ответа.

Таблица перечисляет то, что реально встречается в корпусе (кириллица и латиница).
Неизвестная единица остаётся как есть: сравнение тогда идёт по строке, а не по величине.
"""
import re

# (размерность, множитель к СИ)
UNITS = {
    'м': ('length', 1.0), 'метр': ('length', 1.0), 'мetr': ('length', 1.0),
    'км': ('length', 1e3), 'см': ('length', 1e-2), 'мм': ('length', 1e-3),
    'дм': ('length', 0.1), 'мкм': ('length', 1e-6), 'нм': ('length', 1e-9),
    'км2': ('length2', 1e6), 'м2': ('length2', 1.0), 'см2': ('length2', 1e-4),
    'мм2': ('length2', 1e-6), 'дм2': ('length2', 1e-2), 'м2/с': ('diff', 1.0),
    'км/ч': ('speed', 1 / 3.6), 'км/с': ('speed', 1e3), 'м/с': ('speed', 1.0),
    'см/с': ('speed', 1e-2), 'м/с2': ('accel', 1.0), 'см/с2': ('accel', 1e-2),
    'мм/с2': ('accel', 1e-3), 'рад/с': ('ang_speed', 1.0),
    'км': ('length', 1e3),
    'м3': ('length3', 1.0), 'см3': ('length3', 1e-6), 'мм3': ('length3', 1e-9),
    'дм3': ('length3', 1e-3), 'л': ('length3', 1e-3), 'мл': ('length3', 1e-6),
    'л/моль': ('vol_per_mol', 1e-3), 'м3/моль': ('vol_per_mol', 1.0),
    'с': ('time', 1.0), 'сек': ('time', 1.0), 'секунд': ('time', 1.0), 'с-1': ('freq', 1.0),
    'мин': ('time', 60.0), 'ч': ('time', 3600.0), 'час': ('time', 3600.0),
    'сут': ('time', 86400.0), 'сутки': ('time', 86400.0), 'год': ('time', 3.15576e7),
    'мс': ('time', 1e-3), 'мкс': ('time', 1e-6), 'нс': ('time', 1e-9),
    'рад': ('angle', 1.0), 'град': ('angle', 0.017453292519943295),
    '°': ('angle', 0.017453292519943295), 'гр': ('angle', 0.017453292519943295),
    'об/с': ('freq', 1.0), 'об/мин': ('freq', 1 / 60.0), 'гц': ('freq', 1.0),
    'кг': ('mass', 1.0), 'г': ('mass', 1e-3), 'т': ('mass', 1e3),
    'мг': ('mass', 1e-6), 'ц': ('mass', 100.0),
    'кг/м3': ('density', 1.0), 'г/см3': ('density', 1e3), 'г/моль': ('molar_mass', 1e-3),
    'кг/моль': ('molar_mass', 1.0), 'моль': ('amount', 1.0),
    'н': ('force', 1.0), 'кн': ('force', 1e3), 'мн': ('force', 1e-6),
    'дж': ('energy', 1.0), 'кдж': ('energy', 1e3), 'мдж': ('energy', 1e-6),
    'мкдж': ('energy', 1e-6),
    'эв': ('energy', 1.602176634e-19), 'квт·ч': ('energy', 3.6e6), 'кал': ('energy', 4.184),
    'вт': ('power', 1.0), 'квт': ('power', 1e3), 'мвт': ('power', 1e-6),
    'па': ('pressure', 1.0), 'кпа': ('pressure', 1e3), 'мпа': ('pressure', 1e6),
    'гпа': ('pressure', 1e9), 'атм': ('pressure', 101325.0),
    'мм рт. ст.': ('pressure', 133.322), 'бар': ('pressure', 1e5),
    'кл': ('charge', 1.0), 'нкл': ('charge', 1e-9), 'мкл': ('charge', 1e-6),
    'пкл': ('charge', 1e-12), 'ккл': ('charge', 1e3),
    'а': ('current', 1.0), 'ма': ('current', 1e-3), 'ка': ('current', 1.0),
    'в': ('voltage', 1.0), 'кв': ('voltage', 1e3), 'мв': ('voltage', 1e-3),
    'ом': ('resistance', 1.0), 'ком': ('resistance', 1e3), 'мком': ('resistance', 1e-6),
    'ф': ('capacitance', 1.0), 'мкф': ('capacitance', 1e-6), 'пф': ('capacitance', 1e-12),
    'нф': ('capacitance', 1e-9), 'гн': ('inductance', 1.0), 'мгн': ('inductance', 1e-3),
    'тл': ('field', 1.0), 'мтл': ('field', 1e-3), 'а/м': ('field_strength', 1.0),
    'в/м': ('field_strength', 1.0), 'в/м2': ('field_grad', 1.0),
    'кл/м2': ('surface_charge', 1.0), 'н/м2': ('surface_charge', 1.0),
    'н/кл': ('field_strength', 1.0), 'н·м2/кл': ('flux', 1.0), 'нм2/кл': ('flux', 1.0),
    'вл/м': ('stiffness', 1.0), 'н/м': ('stiffness', 1.0), 'дж/к': ('entropy', 1.0),
    'дж/(моль·к)': ('molar_entropy', 1.0), 'дж/моль': ('molar_energy', 1.0),
    'к': ('temperature', 1.0), '°к': ('temperature', 1.0), '°с': ('temperature', 1.0),
    'моль/л': ('conc', 1e3), 'л/(моль·с)': ('rate', 1e-3), 'моль/(л·с)': ('rate', 1.0),
    '%': ('ratio', 0.01), 'процентов': ('ratio', 0.01), 'проц.': ('ratio', 0.01),
    'безразм': ('none', 1.0),
}


def _norm_unit(raw):
    u = raw.strip().rstrip('.').lower()
    u = u.replace('\u2032', "'").replace('^', '')
    u = u.replace('\u00b2', '2').replace('\u00b3', '3').replace('\u00b9', '1')
    u = re.sub(r'\s+', ' ', u).strip()
    u = re.sub(r'\s+(-?\d+)$', r'\1', u)
    return u


def parse_unit(raw):
    """-> (kind, name, factor). kind: 'known' | 'unknown' | 'none'."""
    u = _norm_unit(raw)
    if not u:
        return ('none', '', 1.0)
    u2 = u.replace('{', '').replace('}', '')
    if u2 in UNITS:
        dim, f = UNITS[u2]
        return ('known', dim, f)
    inv = re.fullmatch(r'(.+?)-1(?![\d-])', u2)
    if inv and inv.group(1) in UNITS:
        dim, f = UNITS[inv.group(1)]
        return ('known', dim + '^-1', 1.0 / f)
    squared = re.fullmatch(r'([a-zа-яё/·\s]+?)[2](?![a-zа-яё])', u2)
    if squared and squared.group(1) in UNITS:
        dim, f = UNITS[squared.group(1)]
        return ('known', dim + '2', f * f)
    cubed = re.fullmatch(r'([a-zа-яё/·\s]+?)[3](?![a-zа-яё])', u2)
    if cubed and cubed.group(1) in UNITS:
        dim, f = UNITS[cubed.group(1)]
        return ('known', dim + '3', f ** 3)
    return ('unknown', u2, 1.0)
