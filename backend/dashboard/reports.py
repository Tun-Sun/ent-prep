"""Генерация PDF-отчёта по прогрессу ученика (reportlab)."""

from io import BytesIO
from pathlib import Path

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ── Шрифты с кириллицей ─────────────────────────────────────────────────────
# Основной вариант — DejaVu, положен в репозиторий (backend/assets/fonts).
# Fallback — системные шрифты (Windows: Arial, тоже с кириллицей).
_FONT_CANDIDATES = {
    'DejaVu': ['DejaVuSans.ttf', 'arial.ttf', 'LiberationSans-Regular.ttf'],
    'DejaVu-Bold': ['DejaVuSans-Bold.ttf', 'arialbd.ttf', 'LiberationSans-Bold.ttf'],
}
_FONT_DIRS = [
    Path(settings.BASE_DIR) / 'assets' / 'fonts',
    Path('/usr/share/fonts/truetype/dejavu'),
    Path('C:/Windows/Fonts'),
    Path('/usr/share/fonts/truetype/liberation'),
]

_fonts_registered = False


def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    missing = []
    for name, candidates in _FONT_CANDIDATES.items():
        for d in _FONT_DIRS:
            found = next((d / c for c in candidates if (d / c).exists()), None)
            if found:
                pdfmetrics.registerFont(TTFont(name, str(found)))
                break
        else:
            missing.append(name)
    if missing:
        raise RuntimeError(f'Не найден шрифт для PDF-отчёта: {", ".join(missing)}')
    _fonts_registered = True


PRIMARY = colors.HexColor('#243B82')
LIGHT = colors.HexColor('#EEF2FA')
GRAY = colors.HexColor('#6B7280')

_h1 = ParagraphStyle('h1', fontName='DejaVu-Bold', fontSize=18, leading=22, textColor=PRIMARY)
_h2 = ParagraphStyle('h2', fontName='DejaVu-Bold', fontSize=13, leading=16, textColor=PRIMARY, spaceBefore=14)
_normal = ParagraphStyle('normal', fontName='DejaVu', fontSize=9.5, leading=13)
_small = ParagraphStyle('small', fontName='DejaVu', fontSize=8.5, leading=11, textColor=GRAY)


def build_student_report(student, stats, subjects, weak_topics, forecast, recent):
    """Собирает PDF-отчёт. Возвращает bytes.

    stats: {total_tests, avg_score, best_score, streak}
    subjects: [{name, tests, avg, best}]
    weak_topics: [{topic, subject, accuracy}]
    forecast: {score, trend, max_score} | None
    recent: [{date, label, score}]
    """
    _register_fonts()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f'Отчёт по прогрессу — {student.full_name or student.username}',
    )

    story = []
    story.append(Paragraph('ENT Prep — отчёт по прогрессу', _h1))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f'Ученик: <b>{student.full_name or student.username}</b> '
        f'(@{student.username})'
        + (f' · Школа: {student.school}' if getattr(student, 'school', '') else ''),
        _normal,
    ))
    from django.utils import timezone
    story.append(Paragraph(
        f'Дата формирования: {timezone.localdate().strftime("%d.%m.%Y")}', _small))
    story.append(Spacer(1, 10))

    # Общая статистика
    story.append(Paragraph('Общая статистика', _h2))
    gen_stats = [
        ['Тестов пройдено', 'Средний балл', 'Лучший балл', 'Серия дней'],
        [str(stats.get('total_tests', 0)), f"{stats.get('avg_score', 0)}%",
         f"{stats.get('best_score', 0)}%", f"{stats.get('streak', 0)}"],
    ]
    t = Table(gen_stats, colWidths=[45 * mm] * 4)
    t.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'DejaVu-Bold', 8.5),
        ('FONT', (0, 1), (-1, 1), 'DejaVu', 11),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    story.append(t)

    # Прогноз ЕНТ
    if forecast:
        story.append(Paragraph('Прогноз балла ЕНТ', _h2))
        trend_labels = {'rising': 'растёт ↗', 'falling': 'падает ↘', 'stable': 'стабильно →'}
        trend = trend_labels.get(forecast.get('trend'), '—')
        story.append(Paragraph(
            f'Прогнозируемый балл: <b>{forecast["score"]}</b> из {forecast.get("max_score", 140)} '
            f'· динамика: <b>{trend}</b>', _normal))
        if forecast.get('sections'):
            rows = [['Предмет', 'Прогноз', 'Порог ЕНТ', 'Статус']]
            for s in forecast['sections']:
                rows.append([
                    s['name'], str(s['score']), str(s['threshold']),
                    '✓ проходит' if s['passes'] else '✗ не проходит',
                ])
            t = Table(rows, colWidths=[55 * mm, 25 * mm, 25 * mm, 45 * mm])
            t.setStyle(TableStyle([
                ('FONT', (0, 0), (-1, 0), 'DejaVu-Bold', 8.5),
                ('FONT', (0, 1), (-1, -1), 'DejaVu', 9),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t)

    # Результаты по предметам
    if subjects:
        story.append(Paragraph('Результаты по предметам', _h2))
        rows = [['Предмет', 'Тестов', 'Средний', 'Лучший']]
        for s in subjects:
            rows.append([s['name'], str(s['tests']), f"{s['avg']}%", f"{s['best']}%"])
        t = Table(rows, colWidths=[70 * mm, 25 * mm, 30 * mm, 30 * mm])
        t.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, 0), 'DejaVu-Bold', 8.5),
            ('FONT', (0, 1), (-1, -1), 'DejaVu', 9),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

    # Слабые темы
    if weak_topics:
        story.append(Paragraph('Слабые темы (точность ниже 50%)', _h2))
        for wt in weak_topics:
            story.append(Paragraph(
                f"• {wt['topic']} <font color='#6B7280'>({wt['subject']})</font> — "
                f"<b>{wt['accuracy']}%</b>", _normal))
    else:
        story.append(Paragraph('Слабые темы: не выявлены — отличная работа!', _normal))

    # Последние тесты
    if recent:
        story.append(Paragraph('Последние тесты', _h2))
        rows = [['Дата', 'Тип', 'Результат']]
        for r in recent:
            rows.append([r['date'], r['label'], r['score']])
        t = Table(rows, colWidths=[30 * mm, 80 * mm, 40 * mm])
        t.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, 0), 'DejaVu-Bold', 8.5),
            ('FONT', (0, 1), (-1, -1), 'DejaVu', 9),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

    # Рекомендации
    story.append(Paragraph('Рекомендации', _h2))
    recs = []
    if weak_topics:
        worst = weak_topics[0]
        recs.append(
            f"Приоритет — тема «{worst['topic']}» ({worst['subject']}): "
            f"точность {worst['accuracy']}%. Рекомендуем 2-3 тренировки в неделю."
        )
    if subjects:
        low = min(subjects, key=lambda s: s['avg'])
        if low['avg'] < 60:
            recs.append(
                f"Предмет «{low['name']}» требует внимания (средний {low['avg']}%). "
                f"Разберите ошибки с преподавателем."
            )
    if forecast and forecast.get('trend') == 'falling':
        recs.append('Динамика результатов снижается — стоит пересмотреть план подготовки.')
    if stats.get('total_tests', 0) < 5:
        recs.append('Пройдено мало тестов — для точного прогноза нужно минимум 5-10 тестов.')
    if not recs:
        recs.append('Продолжайте в том же темпе — результаты стабильны и выше среднего.')
    for i, r in enumerate(recs, 1):
        story.append(Paragraph(f'{i}. {r}', _normal))

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        'Отчёт сформирован автоматически платформой ENT Prep · ent.pmci.kz', _small))

    doc.build(story)
    return buf.getvalue()
