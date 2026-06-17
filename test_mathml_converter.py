"""Test the MathML → LaTeX converter against all real structures from variant HTML."""
import re
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from subjects.mathml_conv import mathml_to_latex, convert_single_math


def main():
    # Collect all <math>...</math> blocks from raw HTML files
    samples = []
    for fname in ['variant1_raw.html', 'variant10_raw.html']:
        path = os.path.join(os.path.dirname(__file__), fname)
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
        # Find math blocks; some are wrapped in span.math-chip, some not
        maths = re.findall(r'<math>.*?</math>', html, re.DOTALL)
        seen_sigs = set()
        for m in maths:
            sig = tuple(re.findall(r'<(m\w+|math)\b', m))
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                samples.append((sig, m))

    print(f"Testing {len(samples)} unique MathML structures\n")
    print("=" * 80)

    failures = 0
    for i, (sig, m) in enumerate(samples, 1):
        try:
            latex = mathml_to_latex(m)
            # Quick sanity check: should not contain any < tag
            has_leftover_tags = bool(re.search(r'<[^>]+>', latex))
            mark = "❌" if has_leftover_tags else "✅"
            if has_leftover_tags:
                failures += 1
            print(f"\n{i:3d}. {mark} TAGS: {sig}")
            print(f"     IN : {m[:150]}")
            print(f"     OUT: {latex}")
            if has_leftover_tags:
                leftover = re.findall(r'<[^>]+>', latex)
                print(f"     ⚠️  LEFTOVER TAGS: {leftover}")
        except Exception as e:
            failures += 1
            print(f"\n{i:3d}. ❌ EXCEPTION")
            print(f"     IN : {m[:150]}")
            print(f"     ERR: {type(e).__name__}: {e}")

    print("\n" + "=" * 80)
    print(f"RESULT: {len(samples) - failures}/{len(samples)} OK, {failures} failures")
    return 0 if failures == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
