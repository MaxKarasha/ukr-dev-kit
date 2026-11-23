#!/usr/bin/env python3
"""Перевіряє структуру репозиторію: маніфести плагіна, frontmatter кожного SKILL.md, посилання на файли
всередині скілів, виконувані скрипти. Запускається в CI.

    python3 tools/validate_skills.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors = []


def err(msg):
    errors.append(msg)


def frontmatter(text):
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        return None
    meta = {}
    for line in m.group(1).splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            meta[k.strip()] = v.strip()
    return meta


def main():
    for f in ('.claude-plugin/plugin.json', '.claude-plugin/marketplace.json', 'hooks/hooks.json'):
        try:
            json.load(open(os.path.join(ROOT, f), encoding='utf-8'))
        except (OSError, ValueError) as e:
            err(f'{f}: {e}')
    plugin = json.load(open(os.path.join(ROOT, '.claude-plugin/plugin.json'), encoding='utf-8'))
    market = json.load(open(os.path.join(ROOT, '.claude-plugin/marketplace.json'), encoding='utf-8'))
    if market['plugins'][0].get('version') != plugin.get('version'):
        err('версії в plugin.json і marketplace.json різняться')

    skills_dir = os.path.join(ROOT, 'skills')
    for name in sorted(os.listdir(skills_dir)):
        sd = os.path.join(skills_dir, name)
        if not os.path.isdir(sd):
            continue
        path = os.path.join(sd, 'SKILL.md')
        if not os.path.isfile(path):
            err(f'skills/{name}: немає SKILL.md')
            continue
        text = open(path, encoding='utf-8').read()
        meta = frontmatter(text)
        if meta is None:
            err(f'skills/{name}/SKILL.md: немає frontmatter')
            continue
        if meta.get('name') != name:
            err(f'skills/{name}/SKILL.md: name «{meta.get("name")}» ≠ назві теки')
        desc = meta.get('description', '')
        if not 50 <= len(desc) <= 1024:
            err(f'skills/{name}/SKILL.md: description {len(desc)} символів (треба 50–1024)')
        if len(text.splitlines()) > 500:
            err(f'skills/{name}/SKILL.md: понад 500 рядків — винесіть деталі в references/')
        for ref in set(re.findall(r'`((?:scripts|references|rules|assets)/[\w./-]+)`', text)):
            if '*' in ref:
                continue
            if not os.path.exists(os.path.join(sd, ref)):
                err(f'skills/{name}/SKILL.md: посилання на відсутній файл {ref}')
        scripts = os.path.join(sd, 'scripts')
        for f in os.listdir(scripts) if os.path.isdir(scripts) else []:
            fp = os.path.join(scripts, f)
            if f.endswith('.py') and open(fp, encoding='utf-8').readline().startswith('#!'):
                if not os.access(fp, os.X_OK):
                    err(f'skills/{name}/scripts/{f}: має shebang, але не виконуваний (chmod +x)')
    if errors:
        print('\n'.join('✖ ' + e for e in errors))
        sys.exit(1)
    print('✔ Структура скілів і маніфести в порядку.')


if __name__ == '__main__':
    main()
