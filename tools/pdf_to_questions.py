""" Разбор PDF-теста: отдельные картинки вопросов и заготовка для ответов.

    python tools/pdf_to_questions.py path/to/test.pdf --out out/test01

На выходе:
  questions/0001.png …   — отдельные фрагменты с вопросами
  answers_template.json   — пустой список эталонов (заполнить вручную)
  manifest.json           — что нашлось на каждой странице

Если в PDF нет текстового слоя (скан), скрипт сохраняет страницу целиком —
тогда границы вопросов придётся уточнить вручную.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pymupdf


def extract(pdf: Path, out: Path, dpi: int = 150) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    images = out / 'questions'
    images.mkdir(exist_ok=True)

    doc = pymupdf.open(pdf)
    scale = dpi / 72
    items = []

    for page_no, page in enumerate(doc, start=1):
        blocks = [b for b in page.get_text('blocks')
                  if len((b[4] or '').strip()) >= 8]
        if blocks:
            # Текстовый слой есть: режем страницу по блокам, каждый блок — вопрос.
            for block in sorted(blocks, key=lambda b: (round(b[1], 1), b[0])):
                rect = pymupdf.Rect(block[:4])
                rect += (-6, -6, -6, -6)  # небольшой отступ вокруг текста
                pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=rect)
                name = f'{len(items) + 1:04d}.png'
                pix.save(str(images / name))
                items.append({
                    'image': f'questions/{name}',
                    'page': page_no,
                    'text': (block[4] or '').strip()[:2000],
                })
        else:
            # Скан: целиком страница, текст не распознан.
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
            name = f'{len(items) + 1:04d}.png'
            pix.save(str(images / name))
            items.append({
                'image': f'questions/{name}',
                'page': page_no,
                'text': '',
            })

    manifest = {
        'source': pdf.name,
        'pages': doc.page_count,
        'questions': items,
    }
    (out / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    template = [
        {'n': i + 1, 'image': item['image'], 'answer': ''}
        for i, item in enumerate(items)
    ]
    (out / 'answers_template.json').write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--dpi', type=int, default=150)
    args = parser.parse_args()

    result = extract(args.pdf, args.out, args.dpi)
    print(f'pages={result["pages"]} fragments={len(result["questions"])}')
    print(f'manifest: {args.out / "manifest.json"}')
    print(f'answers template: {args.out / "answers_template.json"}')
