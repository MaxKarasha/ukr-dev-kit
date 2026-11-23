#!/usr/bin/env python3
"""Піднімає версію ukr-dev-kit одночасно в усіх місцях, де вона записана.

    python3 tools/bump_version.py 0.3.0          # змінити
    python3 tools/bump_version.py --check         # лише перевірити, що всюди однакова (для CI)

Claude Code кешує плагін за версією, PyPI не приймає повторну версію — тож вона має бути однаковою
й новою в маніфестах плагіна, пакеті Python і скриптах скілів.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_FILES = ['src/ukr_dev_kit/__init__.py', 'skills/ukr-proofread/scripts/ukr_lint.py',
            'skills/ukr-i18n/scripts/i18n_check.py', 'skills/ukr-data/scripts/ukr_data.py',
            'skills/ukr-voice/scripts/ukr_voice.py']
JSON_FILES = {'.claude-plugin/plugin.json': ('version',), '.claude-plugin/marketplace.json': ('plugins', 0, 'version')}
PY_RX = re.compile(r"^__version__ = '([^']+)'", re.M)


def read_all():
    found = {}
    for f in PY_FILES:
        m = PY_RX.search(open(os.path.join(ROOT, f), encoding='utf-8').read())
        found[f] = m.group(1) if m else None
    for f, path in JSON_FILES.items():
        node = json.load(open(os.path.join(ROOT, f), encoding='utf-8'))
        for k in path:
            node = node[k]
        found[f] = node
    return found


def write_all(v):
    for f in PY_FILES:
        p = os.path.join(ROOT, f)
        s = open(p, encoding='utf-8').read()
        open(p, 'w', encoding='utf-8').write(PY_RX.sub(f"__version__ = '{v}'", s, count=1))
    for f in JSON_FILES:
        p = os.path.join(ROOT, f)
        s = open(p, encoding='utf-8').read()
        # точкова заміна, щоб не переформатовувати JSON
        s = re.sub(r'("version":\s*")[^"]+(")', rf'\g<1>{v}\g<2>', s)
        open(p, 'w', encoding='utf-8').write(s)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    if sys.argv[1] == '--check':
        found = read_all()
        if len(set(found.values())) != 1:
            print('✖ Версії різняться:\n' + '\n'.join(f'  {v}  {f}' for f, v in found.items()))
            sys.exit(1)
        print(f'✔ Версія {next(iter(found.values()))} однакова в {len(found)} файлах.')
        return
    v = sys.argv[1]
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[ab]\d+|rc\d+)?', v):
        sys.exit(f'Версія має бути за SemVer, напр. 0.3.0, а не «{v}»')
    write_all(v)
    print(f'Версію змінено на {v}. Далі: CHANGELOG.md, коміт, тег v{v}.')
    found = read_all()
    assert set(found.values()) == {v}, found


if __name__ == '__main__':
    main()
