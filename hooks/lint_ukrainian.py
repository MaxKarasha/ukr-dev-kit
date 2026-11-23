#!/usr/bin/env python3
"""Хук PostToolUse: після Write/Edit українського файлу вичитує його й повертає агенту помилки.

Тихий за замовчуванням: перевіряє лише файли, що схожі на українські (локалі uk/uk-UA або текст,
де є і/ї/є/ґ і немає ы/э/ъ/ё), показує лише помилки й попередження у змінених файлах, не більше 12.
Вимкнути: змінна UKR_LINT_HOOK=0 або "hook": false у .ukr-lint.json проєкту.
Хук ніколи не блокує роботу: за будь-якої проблеми він мовчки завершується.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'ukr-proofread', 'scripts'))

LOCALE = re.compile(r'(^|[/\\._-])(uk|uk[-_]UA|ua)([/\\._-]|$)')
TEXTY = {'.md', '.mdx', '.txt', '.rst', '.json', '.arb', '.yml', '.yaml', '.po', '.properties', '.xml',
         '.strings', '.resx', '.html', '.vue', '.svelte'}
MAX = 12


def main():
    if os.environ.get('UKR_LINT_HOOK', '1') == '0':
        return
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    path = (data.get('tool_input') or {}).get('file_path') or ''
    if not path or not os.path.isfile(path) or os.path.splitext(path)[1].lower() not in TEXTY:
        return
    try:
        text = open(path, encoding='utf-8').read()
    except (OSError, UnicodeDecodeError):
        return
    if len(text) > 2_000_000:
        return
    rel = os.path.relpath(path, data.get('cwd') or os.getcwd())
    is_locale = bool(LOCALE.search(rel))
    ukrainian = re.search('[іїєґІЇЄҐ]', text) and len(re.findall('[ыэъёЫЭЪЁ]', text)) < 3
    if not (is_locale or ukrainian):
        return
    import ukr_lint
    cfg = ukr_lint.load_config(os.path.dirname(os.path.abspath(path)))
    try:
        raw = json.load(open(cfg.path, encoding='utf-8')) if cfg.path else {}
    except (OSError, ValueError):
        raw = {}
    if raw.get('hook') is False:
        return
    issues, _ = ukr_lint.lint_file(ukr_lint.Linter(cfg), rel, text)
    issues = [i for i in issues if i.level in ('error', 'warning')]
    if not issues:
        return
    lines = [f'{i.line}:{i.col} {"помилка" if i.level == "error" else "увага"}: {i.message} [{i.rule}]'
             for i in issues[:MAX]]
    more = f'\n… і ще {len(issues) - MAX}. Повний список: ukr_lint.py {rel}' if len(issues) > MAX else ''
    fixable = sum(1 for i in issues if i.fix is not None)
    n = len(issues)
    msg = (f'ukr-lint: у {rel} {n} {ukr_lint.plural(n, "проблема", "проблеми", "проблем")} з українською:\n' + '\n'.join(lines) + more
           + (f'\n{fixable} з них виправляються автоматично: python3 "{ROOT}/skills/ukr-proofread/scripts/ukr_lint.py" --fix {rel}'
              if fixable else '')
           + '\nВиправ їх, якщо це не навмисно (див. скіл ukr-proofread).')
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': msg}},
                     ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:          # хук не має права ламати роботу агента
        pass
