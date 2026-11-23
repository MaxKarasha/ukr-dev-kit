#!/usr/bin/env python3
"""ukr-i18n check — перевірка української локалізації відносно базової (англійської) мови.

    i18n_check.py locales/en.json locales/uk.json      # пара файлів
    i18n_check.py --auto [тека]                          # знайти всі українські локалі й їхні базові файли
    i18n_check.py uk.po                                  # gettext перевіряється й сам по собі
    i18n_check.py --auto --lint                          # ще й вичитати переклади (ukr-lint)
    i18n_check.py --auto --format json|github

Формати: JSON/ARB (i18next, vue-i18n, ICU MessageFormat, Flutter), gettext .po, Android strings.xml,
iOS .strings, .NET .resx, .properties, YAML (якщо встановлено PyYAML).

Що шукає: пропущені й зайві ключі, порожні та неперекладені значення, різні плейсхолдери й теги,
неповні форми множини (українській потрібні one, few, many + other), російські літери,
код мови «ua» замість «uk». Код виходу 1, якщо є помилки (з --strict — і попередження).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from typing import Optional

__version__ = '0.2.0'
HERE = os.path.dirname(os.path.abspath(__file__))
UK_FORMS = ['one', 'few', 'many', 'other']
UK_TOKENS = ['uk-UA', 'uk_UA', 'uk', 'ua', 'ukr']
SKIP_DIRS = {'.git', 'node_modules', 'dist', 'build', 'out', '.next', '.nuxt', '.output', 'vendor', '.venv',
             'venv', '__pycache__', 'bin', 'obj', 'coverage', 'Pods', '.gradle', 'target'}
EXTS = {'.json', '.arb', '.po', '.xml', '.strings', '.resx', '.properties', '.yml', '.yaml'}
RU = re.compile('[ЫыЭэЪъЁё]')
CYR = re.compile('[А-Яа-яІіЇїЄєҐґ]')
PLURAL_KW = r'(?:zero|one|two|few|many|other|=\d+)'


# ════════════════════════════════════ читання форматів ════════════════════════════════════
def flatten(obj, prefix: str = '', out: Optional[dict] = None) -> dict:
    out = {} if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, f'{prefix}.{k}' if prefix else str(k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flatten(v, f'{prefix}[{i}]', out)
    elif obj is not None:
        out[prefix] = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return out


def read_po(path: str) -> tuple:
    """{msgctxt|msgid: msgstr або {індекс: форма}}, заголовок."""
    entries, header = {}, ''
    cur, field = {}, None

    def unq(s):
        return json.loads(s) if s.startswith('"') else s

    def done():
        if 'msgid' in cur:
            key = (cur.get('msgctxt', '') + '\x04' if cur.get('msgctxt') else '') + cur['msgid']
            if cur['msgid'] == '':
                nonlocal header
                header = cur.get('msgstr', '')
            elif not cur.get('obsolete'):
                if 'msgstr_plural' in cur:
                    entries[key] = {'__plural__': True, **cur['msgstr_plural'], '__id_plural__': cur.get('msgid_plural', '')}
                else:
                    entries[key] = cur.get('msgstr', '')

    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if line.startswith('#~'):
            cur['obsolete'] = True
            continue
        if not line or line.startswith('#'):
            if not line and cur:
                done()
                cur, field = {}, None
            continue
        m = re.match(r'(msgctxt|msgid_plural|msgid|msgstr)(?:\[(\d+)\])?\s+(".*")$', line)
        if m:
            if m.group(1) == 'msgctxt' and 'msgid' in cur:
                done()
                cur = {}
            if m.group(1) == 'msgid' and 'msgid' in cur:
                done()
                cur = {}
            if m.group(2) is not None:
                cur.setdefault('msgstr_plural', {})[m.group(2)] = unq(m.group(3))
                field = ('msgstr_plural', m.group(2))
            else:
                cur[m.group(1)] = unq(m.group(3))
                field = m.group(1)
        elif line.startswith('"') and field:
            if isinstance(field, tuple):
                cur['msgstr_plural'][field[1]] += unq(line)
            else:
                cur[field] += unq(line)
    done()
    return entries, header


def read_android(path: str) -> dict:
    out = {}
    root = ET.parse(path).getroot()
    for el in root:
        name = el.get('name')
        if el.get('translatable') == 'false' or not name:
            continue
        if el.tag == 'string':
            out[name] = ''.join(el.itertext())
        elif el.tag == 'plurals':
            out[name] = {'__plural__': True, **{it.get('quantity'): ''.join(it.itertext()) for it in el}}
        elif el.tag == 'string-array':
            for i, it in enumerate(el):
                out[f'{name}[{i}]'] = ''.join(it.itertext())
    return out


def read_resx(path: str) -> dict:
    root = ET.parse(path).getroot()
    out = {}
    for d in root.findall('data'):
        v = d.find('value')
        if d.get('name') and (d.get('type') is None) and v is not None:
            out[d.get('name')] = v.text or ''
    return out


def read_strings(path: str) -> dict:
    raw = open(path, encoding='utf-8-sig').read()
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.S)
    return {json.loads(f'"{k}"'): json.loads(f'"{v}"')
            for k, v in re.findall(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', raw)}


def read_properties(path: str) -> dict:
    out = {}
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line or line[0] in '#!':
            continue
        m = re.match(r'([^=:\s]+)\s*[=:]\s*(.*)$', line)
        if m:
            out[m.group(1)] = m.group(2).encode().decode('unicode_escape') if '\\u' in m.group(2) else m.group(2)
    return out


def load(path: str) -> dict:
    """Будь-який підтримуваний формат → {ключ: рядок | {'__plural__': True, форма: рядок}}."""
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.json', '.arb'):
        data = json.load(open(path, encoding='utf-8-sig'))
        if ext == '.arb':
            data = {k: v for k, v in data.items() if not k.startswith('@')}
        return flatten(data)
    if ext == '.po':
        return read_po(path)[0]
    if ext == '.xml':
        return read_android(path)
    if ext == '.resx':
        return read_resx(path)
    if ext == '.strings':
        return read_strings(path)
    if ext == '.properties':
        return read_properties(path)
    if ext in ('.yml', '.yaml'):
        try:
            import yaml
        except ImportError:
            raise SystemExit('для YAML потрібен PyYAML: pip install pyyaml')
        data = yaml.safe_load(open(path, encoding='utf-8')) or {}
        if isinstance(data, dict) and len(data) == 1 and next(iter(data)) in UK_TOKENS + ['en', 'en-US', 'en_US']:
            data = next(iter(data.values()))           # Rails: {uk: {...}}
        return flatten(data)
    raise SystemExit(f'невідомий формат: {path}')


# ════════════════════════════════════ аналіз значень ════════════════════════════════════
def placeholders(s: str) -> set:
    res = set()
    for m in re.finditer(r'\{\{\s*([\w.]+)\s*\}\}', s):                  # i18next, Angular
        res.add('{{' + m.group(1) + '}}')
    s2 = re.sub(r'\{\{[^{}]*\}\}', '', s)
    for m in re.finditer(r'(?<!\w)\{\s*([A-Za-z_$][\w.$]*|\d+)\s*(?=[,}])', s2):
        before = s2[:m.start()].rstrip()
        if re.search(PLURAL_KW + r'$', before):
            continue
        res.add('{' + m.group(1) + '}')
    for m in re.finditer(r'%(?:\d+\$)?[-+ #0]*\d*(?:\.\d+)?[sdif@]|%\(\w+\)[sdif]', s):  # printf, Python
        res.add(m.group())
    for m in re.finditer(r'(?<![\w:]):([a-z_][a-z0-9_]*)\b', s):          # Laravel :name
        if re.match(r'^[a-z_]+$', m.group(1)) and len(m.group(1)) > 1:
            res.add(':' + m.group(1))
    for m in re.finditer(r'\$t\([^)]*\)|@:[\w.]+', s):                     # посилання i18next / vue-i18n
        res.add(m.group())
    return res


def tags(s: str) -> list:
    return sorted(re.findall(r'</?([A-Za-z][\w-]*|\d+)\b[^<>]*?/?>', s))


def icu_forms(s: str) -> Optional[set]:
    m = re.search(r'\{\s*[\w.]+\s*,\s*plural\s*,', s)
    if not m:
        return None
    return set(re.findall(r'(?:^|[\s}])(zero|one|two|few|many|other|=\d+)\s*\{', s[m.end():]))


def looks_untranslated(base: str, uk: str) -> bool:
    if uk != base or CYR.search(uk):
        return False
    words = re.findall(r'[A-Za-z]{2,}', re.sub(r'\{[^}]*\}|<[^>]*>|https?://\S+|%\w', '', base))
    return len(words) >= 2


# ════════════════════════════════════ перевірки ════════════════════════════════════
class Report:
    def __init__(self):
        self.items = []

    def add(self, level, code, path, key, msg):
        self.items.append({'level': level, 'code': code, 'path': path, 'key': key, 'message': msg})


I18NEXT_SUFFIX = re.compile(r'^(.*)_(zero|one|two|few|many|other)$')


def compare(base: dict, uk: dict, uk_path: str, rep: Report, lint=None) -> None:
    # групи i18next: key_one / key_other
    def groups(d):
        g = {}
        for k in d:
            m = I18NEXT_SUFFIX.match(k)
            if m and not isinstance(d[k], dict):
                g.setdefault(m.group(1), set()).add(m.group(2))
        return g
    bg, ug = groups(base), groups(uk)
    plural_stems = {s for s, f in bg.items() if 'other' in f or 'one' in f}

    for k, bv in base.items():
        m = I18NEXT_SUFFIX.match(k)
        if m and m.group(1) in plural_stems:
            continue                                        # перевіряємо групою нижче
        if k not in uk:
            rep.add('error', 'missing', uk_path, k, 'немає перекладу')
            continue
        check_value(k, bv, uk[k], uk_path, rep, lint)

    for stem in sorted(plural_stems):
        have = ug.get(stem, set())
        if not have and stem in uk:
            continue
        need = [f for f in UK_FORMS if f not in have]
        if not have:
            rep.add('error', 'missing', uk_path, stem + '_*', 'немає перекладу (форми множини)')
        elif need:
            rep.add('error', 'plural', uk_path, stem + '_*',
                    f'бракує форм множини: {", ".join(stem + "_" + f for f in need)} '
                    f'(українській потрібні one, few, many, other)')
        for f in have:
            bkey = f'{stem}_{f}' if f'{stem}_{f}' in base else f'{stem}_other'
            if bkey in base:
                check_value(f'{stem}_{f}', base[bkey], uk[f'{stem}_{f}'], uk_path, rep, lint, plural_member=True)

    for k in uk:
        m = I18NEXT_SUFFIX.match(k)
        if k not in base and not (m and m.group(1) in plural_stems):
            rep.add('warning', 'extra', uk_path, k, 'ключа немає в базовій мові (застарілий?)')


def check_value(k, bv, uv, path, rep, lint, plural_member=False):
    if isinstance(bv, dict) or isinstance(uv, dict):        # Android plurals, gettext plural
        forms = {f for f in (uv if isinstance(uv, dict) else {}) if not f.startswith('__')}
        if isinstance(uv, dict) and any(f in UK_FORMS for f in forms) and not all(f in forms for f in UK_FORMS):
            rep.add('error', 'plural', path, k, 'бракує форм quantity: '
                    + ', '.join(f for f in UK_FORMS if f not in forms) + ' (потрібні one, few, many, other)')
        for f, v in (uv.items() if isinstance(uv, dict) else []):
            if not f.startswith('__'):
                single(f'{k}[{f}]', next((x for kk, x in bv.items() if not kk.startswith('__')), '')
                       if isinstance(bv, dict) else bv, v, path, rep, lint)
        return
    single(k, bv, uv, path, rep, lint, plural_member)


def single(k, bv, uv, path, rep, lint, plural_member=False):
    if not isinstance(uv, str):
        return
    if not uv.strip():
        if isinstance(bv, str) and bv.strip():
            rep.add('error', 'empty', path, k, 'порожній переклад')
        return
    if RU.search(uv):
        rep.add('error', 'russian', path, k, f'російські літери ({", ".join(sorted(set(RU.findall(uv))))}) — '
                'схоже на неперекладене з російської')
    if isinstance(bv, str):
        if looks_untranslated(bv, uv):
            rep.add('warning', 'untranslated', path, k, f'збігається з оригіналом: «{uv[:60]}»')
        pb, pu = placeholders(bv), placeholders(uv)
        if pb != pu and not (plural_member and pu <= pb):
            miss, extra = pb - pu, pu - pb
            msg = []
            if miss:
                msg.append('бракує ' + ', '.join(sorted(miss)))
            if extra:
                msg.append('зайві ' + ', '.join(sorted(extra)))
            rep.add('error', 'placeholder', path, k, 'плейсхолдери: ' + '; '.join(msg))
        if tags(bv) != tags(uv):
            rep.add('warning', 'tags', path, k, 'HTML-теги / компоненти відрізняються від оригіналу')
        fb, fu = icu_forms(bv), icu_forms(uv)
        if fb is not None:
            if fu is None:
                rep.add('error', 'plural', path, k, 'в оригіналі ICU plural, у перекладі — ні')
            else:
                need = [f for f in UK_FORMS if f not in fu]
                if need:
                    rep.add('error', 'plural', path, k, 'ICU plural без форм: ' + ', '.join(need)
                            + ' (для української: one, few, many, other)')
        if ' | ' in bv and '{' not in bv:
            n = len(uv.split(' | '))
            if n not in (3, 4):
                rep.add('warning', 'plural', path, k, f'vue-i18n: {n} форм через « | »; для української — 3 '
                        '(one | few | many) або 4 (нуль | one | few | many) і власні pluralRules')
    if lint:
        for i in lint.check_text(uv, code=False):
            if i.level in ('error', 'warning'):
                rep.add('warning' if i.level == 'warning' else 'error', 'lint:' + i.rule, path, k, i.message)


def check_po_alone(path: str, rep: Report, lint=None) -> None:
    entries, header = read_po(path)
    m = re.search(r'nplurals\s*=\s*(\d+)', header)
    if m and m.group(1) != '3':
        rep.add('error', 'plural', path, '(header)', f'Plural-Forms: nplurals={m.group(1)}, для української — 3')
    elif not m and any(isinstance(v, dict) for v in entries.values()):
        rep.add('error', 'plural', path, '(header)', 'немає Plural-Forms; для української: '
                'nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);')
    for k, v in entries.items():
        msgid = k.split('\x04')[-1]
        if isinstance(v, dict):
            forms = {f: x for f, x in v.items() if not f.startswith('__')}
            if any(not x.strip() for x in forms.values()) or len(forms) < 3:
                rep.add('error', 'plural', path, msgid[:50], 'потрібні 3 форми msgstr[0..2] (1 файл / 2 файли / 5 файлів)')
            for f, x in forms.items():
                single(f'{msgid[:40]}[{f}]', msgid if f == '0' else v.get('__id_plural__', msgid), x, path, rep, lint, True)
        elif not v.strip():
            rep.add('error', 'empty', path, msgid[:50], 'порожній msgstr')
        else:
            single(msgid[:50], msgid, v, path, rep, lint)


# ════════════════════════════════════ пошук файлів ════════════════════════════════════
def _sub_token(path: str, tok: str, repl: str) -> Optional[str]:
    rx = re.compile(r'(?<=[/\\._-])' + re.escape(tok) + r'(?=[/\\._-])|(?<=values-)' + re.escape(tok) + r'(?=[/\\])')
    if not rx.search(path):
        return None
    new = rx.sub(repl, path, count=1)
    return new.replace('values-/', 'values/').replace('.-', '.').replace('..', '.').replace('_.', '.')


def base_for(uk_path: str, base_langs: list) -> Optional[str]:
    p = '/' + uk_path.replace(os.sep, '/')
    for tok in UK_TOKENS:
        for bl in base_langs + ['']:
            cand = _sub_token(p, tok, bl)
            if cand:
                cand = cand[1:].replace('/', os.sep)
                cand = re.sub(r'([/\\])\.', r'\1', cand)
                if os.path.isfile(cand) and os.path.abspath(cand) != os.path.abspath(uk_path):
                    return cand
    return None


def discover(root: str) -> list:
    found = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith('.'))
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() not in EXTS:
                continue
            fp = os.path.join(d, f)
            rel = os.path.relpath(fp, root)
            tail = '/' + rel.replace(os.sep, '/')
            tok = next((t for t in UK_TOKENS if re.search(r'(?<=[/._-])' + re.escape(t) + r'(?=[/._-])', tail)), None)
            if tok and not re.search(r'(package|tsconfig|composer|manifest)', f):
                found.append((fp, tok))
    return found


# ════════════════════════════════════ CLI ════════════════════════════════════
def load_linter():
    for cand in (os.path.join(HERE, '..', '..', 'ukr-proofread', 'scripts'),):
        if os.path.isfile(os.path.join(cand, 'ukr_lint.py')):
            sys.path.insert(0, os.path.abspath(cand))
            import ukr_lint
            return ukr_lint.Linter(ukr_lint.load_config(os.getcwd()))
    raise SystemExit('--lint потребує скіла ukr-proofread поруч (skills/ukr-proofread)')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='ukr-i18n', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='*', help='BASE UK, або один .po')
    ap.add_argument('--auto', nargs='?', const='.', metavar='DIR', help='знайти українські локалі в теці')
    ap.add_argument('--base-lang', default='en,en-US,en_US,en-GB', help='базова мова для --auto')
    ap.add_argument('--lint', action='store_true', help='вичитати переклади (ukr-lint)')
    ap.add_argument('--format', choices=['text', 'json', 'github'], default='text')
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--version', action='version', version=f'ukr-i18n {__version__}')
    a = ap.parse_args(argv)
    rep = Report()
    lint = load_linter() if a.lint else None
    pairs = []
    if a.auto:
        for fp, tok in discover(a.auto):
            if tok == 'ua':
                rep.add('warning', 'locale-code', fp, '', '«ua» — код країни. Код української мови — «uk» (ISO 639-1), '
                        'локаль — «uk-UA»')
            if fp.endswith('.po'):
                pairs.append((None, fp))
                continue
            b = base_for(fp, [x.strip() for x in a.base_lang.split(',')])
            if b:
                pairs.append((b, fp))
            else:
                rep.add('warning', 'no-base', fp, '', 'не знайдено базового файлу для порівняння')
        if not pairs and not rep.items:
            print('Українських файлів локалізації не знайдено.', file=sys.stderr)
            return 0
    elif len(a.files) == 2:
        pairs = [(a.files[0], a.files[1])]
    elif len(a.files) == 1 and a.files[0].endswith(('.po', '.pot')):
        pairs = [(None, a.files[0])]
    else:
        ap.print_help()
        return 2

    for b, u in pairs:
        try:
            if b is None:
                check_po_alone(u, rep, lint)
            else:
                compare(load(b), load(u), u, rep, lint)
        except (ValueError, ET.ParseError) as e:
            rep.add('error', 'parse', u, '', f'не вдалося прочитати: {e}')

    items = rep.items
    if a.format == 'json':
        print(json.dumps(items, ensure_ascii=False, indent=2))
    elif a.format == 'github':
        kind = {'error': 'error', 'warning': 'warning'}
        for i in items:
            print(f'::{kind[i["level"]]} file={i["path"]},title=ukr-i18n {i["code"]}::{i["key"]}: {i["message"]}')
    else:
        color = (sys.stdout.isatty() or bool(os.environ.get('FORCE_COLOR'))) and not os.environ.get('NO_COLOR')
        c = (lambda s, k: f'\033[{k}m{s}\033[0m') if color else (lambda s, k: s)
        cur = None
        for i in items:
            if i['path'] != cur:
                cur = i['path']
                print('\n' + c(cur, '1;4'))
            lvl = c('помилка' if i['level'] == 'error' else 'увага  ', '31' if i['level'] == 'error' else '33')
            print(f'  {lvl}  {c(i["key"], "1")}  {i["message"]}  {c("[" + i["code"] + "]", "2")}')
        ne = sum(1 for i in items if i['level'] == 'error')
        nw = len(items) - ne
        checked = ', '.join(os.path.basename(u) for _, u in pairs)
        if not items:
            print(c(f'✔ Локалізація в порядку ({checked}).', '32'))
        else:
            print(f'\n{"✖" if ne else "⚠"} помилок: {ne}, попереджень: {nw}. Перевірено: {checked}.')
    bad = any(i['level'] == 'error' for i in items) or (a.strict and items)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
