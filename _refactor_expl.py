"""One-off: rewrite clean_explanation steps 3-8 in parse_testent.py."""
import io

path = r'C:\Users\user\ZCodeProject\ent-prep\backend\subjects\management\commands\parse_testent.py'
with io.open(path, encoding='utf-8') as f:
    src = f.read()

OLD_START = "    # 3) Превращаем шаги в аккуратные абзацы.\n"
OLD_END = "    explanation = re.sub(r'\\n{3,}', '\\n\\n', explanation)\n    return explanation.strip()\n"

i = src.index(OLD_START)
j = src.index(OLD_END, i) + len(OLD_END)

NEW = (
    "    # 3) Заголовок шага: <div class=\"step-title\">Шаг 1</div> → <strong>Шаг 1.</strong>\n"
    "    explanation = re.sub(\n"
    "        r'<div\\s+class=[\"\\']step-title[\"\\']\\s*>(.*?)</div>',\n"
    "        lambda m: '<strong>' + m.group(1).strip().rstrip('.') + '.</strong> ',\n"
    "        explanation,\n"
    "        flags=re.DOTALL,\n"
    "    )\n"
    "\n"
    "    # 4) Внутренние <div>...</div> (контент шага) разворачиваем в текст — они\n"
    "    #    не должны становиться блочными <p>, иначе получатся вложенные <p>.\n"
    "    #    Делаем это ДО оборачивания блоков в <p>.\n"
    "    explanation = re.sub(r'<div\\b[^>]*>', '', explanation)\n"
    "    explanation = explanation.replace('</div>', '')\n"
    "\n"
    "    # 5) Строка 'Ответ: ...' — оборачиваем в <p>. После шага 4 обёрток div нет,\n"
    "    #    ищем по якорю <strong>Ответ:</strong> до следующего <strong>Шаг или конца.\n"
    "    explanation = re.sub(\n"
    "        r'(<strong>Ответ:</strong>)(.*?)(?=\\n\\s*<strong>Шаг|\\Z)',\n"
    "        lambda m: '<p>' + m.group(1) + ' ' + m.group(2).strip() + '</p>\\n',\n"
    "        explanation,\n"
    "        flags=re.DOTALL,\n"
    "    )\n"
    "\n"
    "    # 6) Каждый шаг теперь имеет вид '  <strong>Шаг N.</strong> контент'.\n"
    "    #    Оборачиваем блок от <strong>Шаг до следующего <strong>Шаг/конца в <p>.\n"
    "    def _wrap_steps(text):\n"
    "        out = []\n"
    "        for part in re.split(r'(?=<strong>Шаг\\s)', text):\n"
    "            s = part.strip()\n"
    "            if not s:\n"
    "                continue\n"
    "            if s.startswith('<p>'):\n"
    "                out.append(s)\n"
    "            else:\n"
    "                out.append('<p>' + s + '</p>')\n"
    "        return '\\n'.join(out)\n"
    "\n"
    "    explanation = _wrap_steps(explanation)\n"
    "\n"
    "    # 7) Разжимаем сущности\n"
    "    explanation = html_module.unescape(explanation)\n"
    "\n"
    "    # 8) Чистим пустые абзацы, лишние пробелы и переводы строк\n"
    "    explanation = re.sub(r'<p>\\s*</p>', '', explanation)\n"
    "    explanation = re.sub(r'[ \\t]{2,}', ' ', explanation)\n"
    "    explanation = re.sub(r'\\n{3,}', '\\n\\n', explanation)\n"
    "    return explanation.strip()\n"
)

new_src = src[:i] + NEW + src[j:]
with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(new_src)

print("OK; new length =", len(new_src), "was", len(src))
