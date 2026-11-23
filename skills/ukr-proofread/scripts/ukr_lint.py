#!/usr/bin/env python3
"""ukr-lint — вичитка українських текстів: суржик, кальки, типографіка, змішані алфавіти.

Лише стандартна бібліотека Python 3.9+. Працює з текстом, Markdown, JSON/ARB, YAML, .po, .properties,
XML/HTML/Vue і рядками в коді (JS/TS, Python, C#, Java, Kotlin, Swift, Dart, Go, PHP, Ruby).

    ukr_lint.py README.md docs/ src/locales/uk.json   # файли й теки
    ukr_lint.py -t "Прийміть участь у міроприємстві"   # текст із командного рядка
    echo "текст" | ukr_lint.py --stdin
    ukr_lint.py --diff origin/main                      # лише рядки, змінені відносно гілки
    ukr_lint.py --staged                                # лише те, що додано в індекс git
    ukr_lint.py --fix docs/                             # виправити безпечне (типографіка, алфавіти)
    ukr_lint.py --format json|github ...                # для інструментів і GitHub Actions
    ukr_lint.py --rules [слово]                         # список правил;  --explain ID — пояснення

Рівні: error — явна помилка; warning — найімовірніше помилка, залежить від контексту;
hint — стилістична порада (показується з --level hint).
Код виходу: 0 — чисто; 1 — є помилки (з --strict — і попередження); 2 — помилка запуску.
"""
from __future__ import annotations

import argparse
import bisect
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Optional

__version__ = '0.1.0'

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_DIR = os.path.join(os.path.dirname(HERE), 'rules')

LEVELS = {'hint': 0, 'warning': 1, 'error': 2}
LEVEL_UK = {'error': 'помилка', 'warning': 'увага', 'hint': 'порада'}
CATEGORY_UK = {'surzhyk': 'суржик', 'calque': 'калька', 'style': 'правопис', 'term': 'термін',
               'typography': 'типографіка', 'alphabet': 'алфавіт', 'euphony': 'милозвучність'}

CYR = 'А-Яа-яЁёІіЇїЄєҐґ'
UK_ONLY = 'ІіЇїЄєҐґ'
RU_ONLY = 'ЫыЭэЪъЁё'
APOS = "ʼ’'‘`ʹ′"
HAS_CYR = re.compile(f'[{CYR}]')
LB = f"(?<![\\w{APOS}-])"
RB = f"(?![\\w{APOS}])"

SKIP_DIRS = {'.git', 'node_modules', 'dist', 'build', 'out', '.next', '.nuxt', '.output', 'vendor', '.venv',
             'venv', '__pycache__', '.idea', '.vscode', 'coverage', 'target', 'bin', 'obj', '.gradle', 'Pods'}
TEXT_EXT = {'.md', '.markdown', '.mdx', '.txt', '.rst', '.adoc', '.csv'}
JSON_EXT = {'.json', '.arb', '.jsonc'}
YAML_EXT = {'.yml', '.yaml'}
MARKUP_EXT = {'.html', '.htm', '.vue', '.svelte', '.xml', '.xhtml', '.astro'}
CODE_EXT = {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.py', '.cs', '.java', '.kt', '.kts', '.swift', '.dart',
            '.go', '.php', '.rb', '.rs', '.c', '.cc', '.cpp', '.h', '.hpp', '.m', '.scala', '.strings', '.cshtml',
            '.razor', '.resx'}
OTHER_EXT = {'.po', '.pot', '.properties', '.ftl'}
ALL_EXT = TEXT_EXT | JSON_EXT | YAML_EXT | MARKUP_EXT | CODE_EXT | OTHER_EXT


# ════════════════════════════════════ дані ════════════════════════════════════
@dataclass
class Issue:
    start: int                  # позиція в тексті сегмента
    end: int
    level: str
    rule: str                   # «категорія/ключ»
    message: str
    suggestion: str = ''
    fix: Optional[str] = None   # заміна для [start:end], якщо виправлення безпечне
    # заповнюється під час звіту
    path: str = ''
    line: int = 0
    col: int = 0
    excerpt: str = ''

    def as_dict(self) -> dict:
        return {'path': self.path, 'line': self.line, 'col': self.col, 'level': self.level, 'rule': self.rule,
                'text': self.excerpt, 'message': self.message, 'suggestion': self.suggestion,
                'fixable': self.fix is not None}


@dataclass
class Segment:
    """Шматок тексту для перевірки. kind='raw' — точний зріз файлу (offset), kind='json' — розкодований рядок
    JSON; виправлення тоді перекодовуються в токен token=(start, end)."""
    text: str
    offset: int
    kind: str = 'raw'
    token: tuple = ()
    code: bool = False          # рядок із коду: лапки й апострофи там можуть бути синтаксисом — без автозамін


@dataclass
class Rule:
    id: str
    level: str
    regex: re.Pattern
    suggestion: str
    explanation: str
    category: str
    pattern: str = ''


@dataclass
class Config:
    apostrophe: str = 'ʼ'
    disable: list = field(default_factory=list)
    ignore: list = field(default_factory=list)
    allow: list = field(default_factory=list)
    levels: dict = field(default_factory=dict)
    path: str = ''

    def enabled(self, rule: str) -> bool:
        cat = rule.split('/', 1)[0]
        return not any(d in (rule, cat, rule.split('/', 1)[-1]) for d in self.disable)


def load_config(start: str, explicit: Optional[str] = None) -> Config:
    """Шукає .ukr-lint.json від теки start угору до кореня git-репозиторію чи файлової системи."""
    path = explicit
    if not path:
        d = os.path.abspath(start)
        while True:
            cand = os.path.join(d, '.ukr-lint.json')
            if os.path.isfile(cand):
                path = cand
                break
            if os.path.isdir(os.path.join(d, '.git')) or os.path.dirname(d) == d:
                break
            d = os.path.dirname(d)
    cfg = Config()
    if path:
        try:
            data = json.load(open(path, encoding='utf-8'))
        except (OSError, ValueError) as e:
            raise SystemExit(f'ukr-lint: не вдалося прочитати {path}: {e}')
        for k in ('apostrophe', 'disable', 'ignore', 'allow', 'levels'):
            if k in data:
                setattr(cfg, k, data[k])
        cfg.path = path
    return cfg


# ════════════════════════════════════ правила-словники ════════════════════════════════════
def load_rules(rules_dir: str = RULES_DIR) -> list:
    """Читає rules/*.txt. Рядок: «ключ | рівень | шаблон | заміна | пояснення».
    Шаблон — регулярний вираз без урахування регістру; межі слова додаються автоматично,
    пробіл у шаблоні означає «будь-які пробіли». Заміна, що починається з «=», — шаблон re.expand
    (\\1, \\2…): таке правило виправляється автоматично (--fix). Розділювач — « | » з пробілами, тож «|» без пробілів
    лишається альтернативою в регулярному виразі."""
    rules = []
    seen = set()
    for name in sorted(os.listdir(rules_dir)):
        if not name.endswith('.txt'):
            continue
        category = name[:-4]
        for n, line in enumerate(open(os.path.join(rules_dir, name), encoding='utf-8'), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split(' | ')]
            if len(parts) != 5:
                raise SystemExit(f'{name}:{n}: очікую 5 полів через « | », маю {len(parts)}')
            key, level, pattern, suggestion, explanation = parts
            if level not in LEVELS:
                raise SystemExit(f'{name}:{n}: невідомий рівень «{level}»')
            rid = f'{category}/{key}'
            if rid in seen:
                raise SystemExit(f'{name}:{n}: правило {rid} уже є')
            seen.add(rid)
            body = pattern.replace(' ', r'\s+')
            try:
                rx = re.compile(f'{LB}(?:{body}){RB}', re.I)
            except re.error as e:
                raise SystemExit(f'{name}:{n}: поганий шаблон: {e}')
            rules.append(Rule(rid, level, rx, suggestion, explanation, category, pattern))
    return rules


# ════════════════════════════════════ вбудовані перевірки ════════════════════════════════════
L2C = dict(zip('aceiopxyABCEHIKMOPTXïÏ', 'асеіорхуАВСЕНІКМОРТХїЇ'))
C2L = {v: k for k, v in L2C.items()}
WORD_MIXED = re.compile(f"[A-Za-zïÏ{CYR}]+")
LAT = re.compile('[A-Za-zïÏ]')
CYR_RE = re.compile(f'[{CYR}]')

V = 'аеєиіїоуюяАЕЄИІЇОУЮЯ'
C = 'бвгґджзйклмнпрстфхцчшщьБВГҐДЖЗЙКЛМНПРСТФХЦЧШЩЬ'

BUILTIN_DOC = {
    'alphabet/mixed': ('error', 'Слово змішує латиницю й кирилицю (схожі літери: a/а, i/і, o/о, p/р, c/с…). '
                       'Такі слова не знаходить пошук, їх не розпізнає перевірка правопису й озвучка.'),
    'alphabet/russian-letter': ('error', 'У слові є літера, якої немає в українській абетці: ы, э, ъ, ё.'),
    'alphabet/russian-text': ('hint', 'Шматок схожий на російський текст (є ы/э/ъ/ё й немає і/ї/є/ґ) — пропущено.'),
    'typography/apostrophe': ('warning', 'Апостроф — один символ на весь проєкт. Рекомендовано ʼ (U+02BC): '
                              'це літера, тож слово «пʼять» не розривається в пошуку й виділенні. '
                              'Інший вибір задайте в .ukr-lint.json: {"apostrophe": "’"}.'),
    'typography/quotes': ('warning', 'Українські лапки — «ялинки»; внутрішні — „лапки“. Прямі "…" та англійські “…” — ні.'),
    'typography/dash': ('warning', 'Між словами — тире «—» з пробілами, а не дефіс «-».'),
    'typography/en-dash': ('hint', 'Між словами в українському тексті — довге тире «—».'),
    'typography/ellipsis': ('hint', 'Три крапки — один символ «…».'),
    'typography/space-before': ('error', 'Перед комою, крапкою з комою, двокрапкою, знаком оклику чи питання пробілу немає.'),
    'typography/space-after': ('warning', 'Після коми чи крапки з комою потрібен пробіл.'),
    'typography/double-space': ('hint', 'Подвійний пробіл усередині речення.'),
    'typography/repeat': ('warning', 'Слово повторено двічі поспіль — схоже на описку.'),
    'typography/number-format': ('hint', 'В українських текстах тисячі відділяють пробілом (нерозривним), '
                                 'дробову частину — комою: 1 234 567,89.'),
    'typography/decimal-point': ('hint', 'Десятковий знак в українському тексті — кома: 3,5 млн.'),
    'typography/currency': ('hint', 'Знак гривні ставлять після суми: 100 ₴ (або «100 грн»).'),
    'euphony/v-u': ('hint', 'Чергування у/в: між голосними — «в», між приголосними — «у» (Правопис, § 23).'),
    'euphony/i-j': ('hint', 'Чергування і/й: після голосного перед приголосним — «й», між приголосними — «і».'),
}

REPEAT_OK = {'так', 'ну', 'ось', 'ще', 'дуже', 'ага', 'годі', 'ой', 'ах', 'ох', 'ха', 'хі', 'ну-ну', 'тук', 'та',
             'ля', 'бла', 'кап', 'тік', 'біп'}


def _issues_builtin(text: str, cfg: Config, code: bool) -> Iterator[Issue]:
    pref = cfg.apostrophe

    # ── алфавіти ──
    for m in WORD_MIXED.finditer(text):
        w = m.group()
        lat = len(LAT.findall(w))
        cyr = len(CYR_RE.findall(w))
        if lat and cyr:
            if cyr >= lat and all(ch in L2C for ch in w if LAT.match(ch)):
                fix = ''.join(L2C.get(ch, ch) if LAT.match(ch) else ch for ch in w)
            elif lat > cyr and all(ch in C2L for ch in w if CYR_RE.match(ch)):
                fix = ''.join(C2L.get(ch, ch) if CYR_RE.match(ch) else ch for ch in w)
            else:
                fix = None
            yield Issue(m.start(), m.end(), 'error', 'alphabet/mixed',
                        f'«{w}» змішує латиницю й кирилицю', fix or '', fix)
        elif cyr and re.search(f'[{RU_ONLY}]', w):
            yield Issue(m.start(), m.end(), 'error', 'alphabet/russian-letter',
                        f'«{w}»: літера {", ".join(sorted(set(re.findall(f"[{RU_ONLY}]", w))))} — не з української абетки')

    # ── апостроф ──
    for m in re.finditer(f"(?<=[бпвмфрзкгґхжчшщтдлнсцБПВМФРЗКГҐХЖЧШЩТДЛНСЦ])([{APOS}\"])(?=[яюєїЯЮЄЇ])", text):
        if m.group(1) != pref and not (code and m.group(1) in '"\''):
            yield Issue(m.start(), m.end(), 'warning', 'typography/apostrophe',
                        f'апостроф «{m.group(1)}» → «{pref}»', pref, pref)

    # ── лапки ──
    for m in re.finditer(r'"([^"\n]{1,300}?)"|“([^“”\n]{1,300}?)”', text):
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        if not HAS_CYR.search(inner) or inner.strip() != inner:
            continue
        fix = None if code and m.group(1) is not None else f'«{inner}»'
        yield Issue(m.start(), m.end(), 'warning', 'typography/quotes', 'лапки — «ялинки»', f'«{inner}»', fix)

    # ── тире ──
    for m in re.finditer(r'(?<=[\w»)”"!?.…])([ \t]+)(-{1,2}|–)([ \t]+)(?=[\w«(„"])', text):
        left, right = text[max(0, m.start() - 20):m.start()], text[m.end():m.end() + 20]
        if not (HAS_CYR.search(left) or HAS_CYR.search(right)):
            continue
        if re.search(r'\d$', left) and re.match(r'\d', right):
            continue                                   # «5 - 3» — це, найпевніше, арифметика
        if m.group(2) == '–':
            yield Issue(m.start(), m.end(), 'hint', 'typography/en-dash', 'між словами — «—»', ' — ', ' — ')
        else:
            yield Issue(m.start(), m.end(), 'warning', 'typography/dash', 'дефіс між словами → тире «—»', ' — ', ' — ')

    # ── три крапки ──
    for m in re.finditer(r'(?<![./\\])\.\.\.(?![./\w])', text):
        if HAS_CYR.search(text[max(0, m.start() - 30):m.end() + 30]):
            yield Issue(m.start(), m.end(), 'hint', 'typography/ellipsis', '«...» → «…»', '…', '…')

    # ── пробіли ──
    for m in re.finditer(f'(?<=[{CYR}»)])[ \t]+(?=[,;:!?](?:\\s|$|[»)”"]))', text):
        yield Issue(m.start(), m.end(), 'error', 'typography/space-before', 'зайвий пробіл перед розділовим знаком',
                    '', '')
    for m in re.finditer(f'(?<=[{CYR}])([,;])(?=[{CYR}])', text):
        yield Issue(m.start(), m.end(), 'warning', 'typography/space-after', 'після розділового знака потрібен пробіл',
                    m.group(1) + ' ', m.group(1) + ' ')
    if not code:
        for m in re.finditer(f'(?<=[{CYR},.;:!?»])[ ]{{2,}}(?=[{CYR}«])', text):
            yield Issue(m.start(), m.end(), 'hint', 'typography/double-space', 'подвійний пробіл', ' ', ' ')

    # ── повтор слова ──
    for m in re.finditer(f"(?<![\\w{APOS}-])([{CYR}{APOS}]{{2,}})[ \\t]+(\\1)(?![\\w{APOS}-])", text, re.I):
        if m.group(1).lower() in REPEAT_OK:
            continue
        yield Issue(m.start(), m.end(), 'warning', 'typography/repeat', f'«{m.group(1)}» двічі поспіль',
                    m.group(1), m.group(1))

    # ── числа й гроші ──
    if HAS_CYR.search(text):
        for m in re.finditer(r'(?<![\d.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d.,])', text):
            uk = m.group().replace(',', ' ').replace('.', ',')
            yield Issue(m.start(), m.end(), 'hint', 'typography/number-format', f'«{m.group()}» → «{uk}»', uk)
        for m in re.finditer(r'(?<![\d.,])\d+\.\d+(?=\s*(?:млн|млрд|тис|%|грн|кг|км|см|мм|ГБ|МБ|ТБ|хв|год|с\b|м\b|л\b))',
                             text):
            yield Issue(m.start(), m.end(), 'hint', 'typography/decimal-point', f'«{m.group()}» → «{m.group().replace(".", ",")}»',
                        m.group().replace('.', ','))
        for m in re.finditer(r'₴\s?\d[\d\s ,.]*', text):
            yield Issue(m.start(), m.end(), 'hint', 'typography/currency', 'знак ₴ — після суми',
                        m.group()[1:].strip() + ' ₴')

    # ── милозвучність ──
    for m in re.finditer(f'(?<=[{V}]) (у) (?=[{V}])', text):
        yield Issue(m.start(1), m.end(1), 'hint', 'euphony/v-u', 'між голосними — «в»', 'в', 'в')
    for m in re.finditer(f'(?<=[{C}]) (в) (?=[{C}])', text):
        yield Issue(m.start(1), m.end(1), 'hint', 'euphony/v-u', 'між приголосними — «у»', 'у', 'у')
    for m in re.finditer(f'(?<=[{V}]) (і) (?=[бвгґджзклмнпрстфхцчшщ])', text):
        yield Issue(m.start(1), m.end(1), 'hint', 'euphony/i-j', 'після голосного перед приголосним — «й»', 'й', 'й')
    for m in re.finditer(f'(?<=[{C}]) (й) (?=[{C}])', text):
        yield Issue(m.start(1), m.end(1), 'hint', 'euphony/i-j', 'між приголосними — «і»', 'і', 'і')


def is_russian(text: str) -> bool:
    return bool(re.search(f'[{RU_ONLY}]', text)) and not re.search(f'[{UK_ONLY}]', text)


# ════════════════════════════════════ ядро ════════════════════════════════════
class Linter:
    def __init__(self, cfg: Optional[Config] = None, rules: Optional[list] = None):
        self.cfg = cfg or Config()
        self.rules = rules if rules is not None else load_rules()
        self.allow = {w.lower() for w in self.cfg.allow}

    def check_text(self, text: str, code: bool = False) -> list:
        """Перевіряє один шматок тексту. Повертає Issue з позиціями в цьому тексті."""
        if not HAS_CYR.search(text):
            return []
        masked = mask(text, code)
        if is_russian(masked):
            return [Issue(0, min(len(text), 40), 'hint', 'alphabet/russian-text', BUILTIN_DOC['alphabet/russian-text'][1])]
        out = list(_issues_builtin(masked, self.cfg, code))
        for r in self.rules:
            for m in r.regex.finditer(masked):
                if r.suggestion.startswith('='):        # шаблон заміни → безпечне виправлення
                    fix = m.expand(r.suggestion[1:])
                    if m.group()[:1].isupper() and fix[:1].islower():
                        fix = fix[:1].upper() + fix[1:]
                    out.append(Issue(m.start(), m.end(), r.level, r.id, f'«{m.group()}» → «{fix}»', fix, fix))
                else:
                    out.append(Issue(m.start(), m.end(), r.level, r.id, f'«{m.group()}» → {r.suggestion}',
                                     r.suggestion))
        res = []
        for i in out:
            if not self.cfg.enabled(i.rule):
                continue
            frag = text[i.start:i.end]
            if frag.lower() in self.allow or MASK in masked[i.start:i.end]:
                continue
            i.level = self.cfg.levels.get(i.rule, i.level)
            res.append(i)
        res.sort(key=lambda i: (i.start, -LEVELS[i.level]))
        return res


MASK = ''
_MASKS = [
    re.compile(r'https?://[^\s)<>"\'»]+|www\.[^\s)<>"\'»]+'),          # адреси
    re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),                              # пошта
    re.compile(r'\{\{[^{}]*\}\}|\{[A-Za-z_$][\w.$]*\}|%\(\w+\)[sdif]|%\d*\$?[sdif@]|\$\{[^}]*\}|:[a-z_]\w*(?=\W|$)'),
    re.compile(r'</?[A-Za-z][^<>]*>'),                                      # HTML-теги
]


_CODE_MASKS = [
    re.compile(r'\\(?:u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)'),                # \n, \", \u0456 у рядках коду
    re.compile(r'\$?\{[^{}\n]*\}'),                                       # вирази f-рядків і шаблонів
]


def mask(text: str, code: bool = False) -> str:
    """Замінює те, що не є людським текстом (адреси, плейсхолдери, теги, а в коді — екранування й вирази
    {…}), символом MASK тієї ж довжини."""
    for rx in (_CODE_MASKS if code else []) + _MASKS:
        text = rx.sub(lambda m: MASK * len(m.group()), text)
    return text


# ════════════════════════════════════ розбір файлів ════════════════════════════════════
_CODE_STR = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`'
                       r'|//[^\n]*|#[^\n]*|/\*.*?\*/|<!--.*?-->', re.S)
_JSON_STR = re.compile(r'"(?:[^"\\]|\\.)*"')


def segments(path: str, text: str) -> Iterator[Segment]:
    ext = os.path.splitext(path)[1].lower()
    if ext in JSON_EXT:
        yield from _json_segments(text)
    elif ext in YAML_EXT or ext == '.properties':
        yield from _kv_segments(text, ext)
    elif ext in ('.po', '.pot'):
        for m in _CODE_STR.finditer(text):
            line_start = text.rfind('\n', 0, m.start()) + 1
            head = text[line_start:m.start()].strip()
            if m.group()[0] == '"' and not head.startswith(('msgid', 'msgctxt', '#')):
                if head == '' and _prev_kw(text, line_start) in ('msgid', 'msgctxt'):
                    continue
                yield Segment(m.group()[1:-1], m.start() + 1, code=True)
    elif ext in MARKUP_EXT:
        yield from _markup_segments(text)
    elif ext in CODE_EXT:
        for m in _CODE_STR.finditer(text):
            s = m.group()
            if not HAS_CYR.search(s):
                continue
            if s[0] in '"\'`':
                yield Segment(s[1:-1], m.start() + 1, code=True)
            else:
                yield Segment(s, m.start(), code=True)
    elif ext in ('.md', '.markdown', '.mdx'):
        yield Segment(_mask_markdown(text), 0)
    else:
        yield Segment(text, 0)


def _prev_kw(text: str, line_start: int) -> str:
    """Для рядків-продовжень у .po: до якого ключового слова належить рядок."""
    pos = line_start
    while pos > 0:
        prev = text.rfind('\n', 0, pos - 1) + 1
        line = text[prev:pos].strip()
        if not line.startswith('"'):
            return line.split(' ', 1)[0].split('[', 1)[0]
        pos = prev
    return ''


def _mask_markdown(text: str) -> str:
    """Код у Markdown (блоки ``` та `рядковий`) і посилання ](…) не перевіряємо."""
    def blank(m):
        return re.sub(r'[^\n]', MASK, m.group())
    text = re.sub(r'^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$', blank, text, flags=re.S | re.M)
    text = re.sub(r'(`+)[^`\n]+?\1', blank, text)
    text = re.sub(r'\]\([^)\n]*\)', blank, text)
    text = re.sub(r'^---\n.*?\n---$', blank, text, count=1, flags=re.S)
    return text


def _json_segments(text: str) -> Iterator[Segment]:
    for m in _JSON_STR.finditer(text):
        after = text[m.end():m.end() + 40].lstrip()
        if after.startswith(':'):
            continue                                   # ключ, а не значення
        try:
            val = json.loads(m.group())
        except ValueError:
            continue
        if HAS_CYR.search(val):
            yield Segment(val, m.start() + 1, kind='json', token=(m.start(), m.end()))


def _kv_segments(text: str, ext: str) -> Iterator[Segment]:
    pos = 0
    for line in text.splitlines(True):
        body = line.rstrip('\r\n')
        if ext == '.properties':
            mm = re.match(r'\s*[^#!\s][^=:]*?\s*[=:]\s*(.*)$', body)
        else:
            mm = re.match(r'\s*(?:-\s+)?(?:[\w.\-]+|"[^"]*"|\'[^\']*\')\s*:\s+(.*)$', body) \
                or re.match(r'\s*-\s+(.*)$', body) or re.match(r'\s*(?!#)(.+)$', body)
        if mm and HAS_CYR.search(mm.group(1)):
            val, start = mm.group(1), pos + mm.start(1)
            if ext != '.properties':
                if re.match(r'\s*#', body):
                    pos += len(line)
                    continue
                cm = re.search(r'\s+#.*$', val)
                if cm and not re.match(r'^["\']', val):
                    val = val[:cm.start()]
                if len(val) >= 2 and val[0] == val[-1] and val[0] in '"\'':
                    val, start = val[1:-1], start + 1
            yield Segment(val, start, code=True)
        pos += len(line)


def _markup_segments(text: str) -> Iterator[Segment]:
    blanked = re.sub(r'<(script|style)\b.*?</\1>', lambda m: ' ' * len(m.group()), text, flags=re.S | re.I)
    for m in re.finditer(r'>([^<>]+)<', blanked):
        if HAS_CYR.search(m.group(1)):
            yield Segment(text[m.start(1):m.end(1)], m.start(1))
    for m in re.finditer(r'<[^<>]+>', blanked):
        for a in re.finditer(r'=\s*"([^"]*)"|=\s*\'([^\']*)\'', m.group()):
            g = 1 if a.group(1) is not None else 2
            if HAS_CYR.search(a.group(g)):
                yield Segment(a.group(g), m.start() + a.start(g), code=True)
    for m in re.finditer(r'<script\b[^>]*>(.*?)</script>', text, flags=re.S | re.I):
        for s in _CODE_STR.finditer(m.group(1)):
            if HAS_CYR.search(s.group()) and s.group()[0] in '"\'`':
                yield Segment(s.group()[1:-1], m.start(1) + s.start() + 1, code=True)


# ════════════════════════════════════ файл: перевірка й виправлення ════════════════════════════════════
_DISABLE_BLOCK = re.compile(r'ukr-lint-disable(?!-)(.*?)(?:ukr-lint-enable|\Z)', re.S)


def ignored_lines(text: str) -> set:
    lines = text.split('\n')
    res = set()
    for n, l in enumerate(lines, 1):
        if 'ukr-lint-disable-line' in l:
            res.add(n)
        if 'ukr-lint-disable-next-line' in l:
            res.add(n + 1)
    for m in _DISABLE_BLOCK.finditer(text):
        a = text.count('\n', 0, m.start()) + 1
        b = text.count('\n', 0, m.end()) + 1
        res.update(range(a, b + 1))
    return res


class FileResult:
    def __init__(self, path: str, text: str, issues: list):
        self.path, self.text, self.issues = path, text, issues


def lint_file(linter: Linter, path: str, text: str, only_lines: Optional[set] = None) -> tuple:
    """Повертає (issues, edits): edits — список (start, end, заміна) у координатах файлу."""
    starts = [0] + [m.end() for m in re.finditer('\n', text)]
    skip = ignored_lines(text)
    issues, edits = [], []
    for seg in segments(path, text):
        found = linter.check_text(seg.text, seg.code)
        if not found:
            continue
        seg_fixes = []
        for i in found:
            pos = seg.offset + (i.start if seg.kind == 'raw' else 0)
            line = bisect.bisect_right(starts, pos)
            col = pos - starts[line - 1] + 1
            if line in skip or (only_lines is not None and line not in only_lines):
                continue
            i.path, i.line, i.col = path, line, col
            i.excerpt = seg.text[i.start:i.end].replace('\n', ' ')
            issues.append(i)
            if i.fix is not None:
                seg_fixes.append(i)
        if seg_fixes:
            edits.extend(_segment_edits(seg, seg_fixes))
    return issues, edits


def _segment_edits(seg: Segment, fixes: list) -> list:
    chosen, last = [], -1
    for i in sorted(fixes, key=lambda i: (i.start, -LEVELS[i.level])):
        if i.start >= last:
            chosen.append(i)
            last = i.end
    if seg.kind == 'raw':
        return [(seg.offset + i.start, seg.offset + i.end, i.fix) for i in chosen]
    new = seg.text
    for i in reversed(chosen):
        new = new[:i.start] + i.fix + new[i.end:]
    return [(seg.token[0], seg.token[1], json.dumps(new, ensure_ascii=False))]


def apply_edits(text: str, edits: list) -> str:
    last = len(text) + 1
    for s, e, r in sorted(edits, key=lambda x: x[0], reverse=True):
        if e <= last:
            text = text[:s] + r + text[e:]
            last = s
    return text


# ════════════════════════════════════ git і пошук файлів ════════════════════════════════════
def git(*args: str) -> str:
    try:
        return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        msg = getattr(e, 'stderr', '') or str(e)
        raise SystemExit(f'ukr-lint: git {" ".join(args)} — {msg.strip()}')


def changed_lines(base: Optional[str], staged: bool) -> dict:
    """{файл: {номери доданих рядків}} з git diff -U0."""
    args = ['diff', '-U0', '--no-color', '--no-ext-diff', '--diff-filter=AMR']
    args += ['--cached'] if staged else [base or 'HEAD']
    root = git('rev-parse', '--show-toplevel').strip()
    res, cur = {}, None
    for line in git(*args).splitlines():
        if line.startswith('+++ '):
            p = line[4:]
            cur = None if p == '/dev/null' else os.path.relpath(os.path.join(root, p[2:] if p.startswith('b/') else p))
            if cur:
                res.setdefault(cur, set())
        elif line.startswith('@@') and cur:
            m = re.match(r'@@ -\S+ \+(\d+)(?:,(\d+))? @@', line)
            if m:
                a, n = int(m.group(1)), int(m.group(2) or 1)
                res[cur].update(range(a, a + n))
    return {p: ls for p, ls in res.items() if ls and os.path.isfile(p)}


def iter_files(paths: Iterable[str], cfg: Config) -> Iterator[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.'))
                for f in sorted(files):
                    fp = os.path.join(root, f)
                    if os.path.splitext(f)[1].lower() in ALL_EXT and not _ignored(fp, cfg):
                        yield fp
        elif os.path.isfile(p):
            yield p                                    # явно названий файл перевіряємо завжди
        else:
            print(f'ukr-lint: немає такого файлу: {p}', file=sys.stderr)


def _ignored(path: str, cfg: Config) -> bool:
    rel = os.path.relpath(path).replace(os.sep, '/')
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(os.path.basename(rel), g) for g in cfg.ignore)


# ════════════════════════════════════ звіт ════════════════════════════════════
def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


class Out:
    def __init__(self, color: bool):
        self.c = color

    def __call__(self, s: str, code: str) -> str:
        return f'\033[{code}m{s}\033[0m' if self.c else s


def report_text(issues: list, rules_by_id: dict, verbose: bool, color: bool, fixable_hint: bool = True) -> None:
    o = Out(color)
    tone = {'error': '31', 'warning': '33', 'hint': '36'}
    cur = None
    for i in issues:
        if i.path != cur:
            cur = i.path
            print('\n' + o(i.path or '<текст>', '1;4'))
        loc = o(f'{i.line}:{i.col}'.rjust(7), '2')
        lvl = o(LEVEL_UK[i.level].ljust(7), tone[i.level])
        cat, key = i.rule.split('/', 1)
        tail = o(f'[{CATEGORY_UK.get(cat, cat)}/{key}]', '2')
        fix = o(' ✎', '32') if i.fix is not None else ''
        print(f'{loc}  {lvl} {i.message}{fix}  {tail}')
        if verbose:
            exp = rules_by_id[i.rule].explanation if i.rule in rules_by_id else BUILTIN_DOC.get(i.rule, ('', ''))[1]
            if exp:
                print(' ' * 18 + o(exp, '2'))
    n = {k: sum(1 for i in issues if i.level == k) for k in LEVELS}
    files = len({i.path for i in issues})
    if not issues:
        print(o('✔ Чисто: проблем не знайдено.', '32'))
        return
    parts = []
    if n['error']:
        parts.append(o(f'{n["error"]} {plural(n["error"], "помилка", "помилки", "помилок")}', '31'))
    if n['warning']:
        parts.append(o(f'{n["warning"]} {plural(n["warning"], "попередження", "попередження", "попереджень")}', '33'))
    if n['hint']:
        parts.append(o(f'{n["hint"]} {plural(n["hint"], "порада", "поради", "порад")}', '36'))
    fx = sum(1 for i in issues if i.fix is not None)
    where = f' у {files} {plural(files, "файлі", "файлах", "файлах")}' if files > 1 else ''
    print(f'\n{"✖" if n["error"] else "⚠"} ' + ', '.join(parts) + where + '.'
          + (f' {fx} можна виправити автоматично: --fix (позначено ✎).' if fx and fixable_hint else ''))


def report_github(issues: list) -> None:
    kind = {'error': 'error', 'warning': 'warning', 'hint': 'notice'}
    for i in issues:
        msg = i.message.replace('%', '%25').replace('\n', '%0A')
        print(f'::{kind[i.level]} file={i.path},line={i.line},col={i.col},title=ukr-lint {i.rule}::{msg}')


# ════════════════════════════════════ CLI ════════════════════════════════════
def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog='ukr-lint', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paths', nargs='*', help='файли або теки')
    ap.add_argument('-t', '--text', help='перевірити цей текст')
    ap.add_argument('--stdin', action='store_true', help='прочитати текст зі stdin')
    ap.add_argument('--diff', nargs='?', const='HEAD', metavar='BASE', help='лише рядки, змінені відносно BASE (типово HEAD)')
    ap.add_argument('--staged', action='store_true', help='лише рядки, додані в індекс git')
    ap.add_argument('--fix', action='store_true', help='застосувати безпечні виправлення (✎)')
    ap.add_argument('--format', choices=['text', 'json', 'github'], default='text')
    ap.add_argument('--level', choices=list(LEVELS), default='warning', help='мінімальний рівень (типово warning)')
    ap.add_argument('--strict', action='store_true', help='код виходу 1 і на попередження')
    ap.add_argument('-v', '--verbose', action='store_true', help='пояснення до кожної знахідки')
    ap.add_argument('--apostrophe', help='символ апострофа проєкту (типово ʼ)')
    ap.add_argument('--config', help='шлях до .ukr-lint.json')
    ap.add_argument('--no-color', action='store_true')
    ap.add_argument('--rules', nargs='?', const='', metavar='ПОШУК', help='показати правила')
    ap.add_argument('--explain', metavar='ID', help='пояснити правило')
    ap.add_argument('--version', action='version', version=f'ukr-lint {__version__}')
    a = ap.parse_args(argv)

    cfg = load_config(os.getcwd(), a.config)
    if a.apostrophe:
        cfg.apostrophe = a.apostrophe
    rules = load_rules()
    by_id = {r.id: r for r in rules}
    color = (sys.stdout.isatty() or bool(os.environ.get('FORCE_COLOR'))) and not a.no_color and not os.environ.get('NO_COLOR')

    if a.rules is not None:
        q = a.rules.lower()
        rows = [(r.id, r.level, r.suggestion, r.explanation) for r in rules] + \
               [(k, v[0], '', v[1]) for k, v in BUILTIN_DOC.items()]
        rows = [r for r in rows if q in ' '.join(r).lower()]
        for rid, lvl, sug, exp in rows:
            print(f'{rid:38s} {lvl:8s} {sug}')
        print(f'\n{len(rows)} {plural(len(rows), "правило", "правила", "правил")}')
        return 0
    if a.explain:
        r = by_id.get(a.explain)
        if r:
            print(f'{r.id} ({r.level})\nЗаміна: {r.suggestion}\n{r.explanation}\nШаблон: {r.pattern}')
        elif a.explain in BUILTIN_DOC:
            print(f'{a.explain} ({BUILTIN_DOC[a.explain][0]})\n{BUILTIN_DOC[a.explain][1]}')
        else:
            print(f'Немає правила {a.explain}. Список: --rules', file=sys.stderr)
            return 2
        return 0

    linter = Linter(cfg, rules)
    minlvl = LEVELS[a.level]
    issues = []

    if a.text is not None or a.stdin:
        text = a.text if a.text is not None else sys.stdin.read()
        found, edits = lint_file(linter, '<текст>.txt', text)
        issues = [i for i in found if LEVELS[i.level] >= minlvl]
        for i in issues:
            i.path = ''
        if a.fix:
            sys.stdout.write(apply_edits(text, [e for e in edits]))
            return 0
    else:
        only = None
        if a.diff or a.staged:
            only = changed_lines(a.diff, a.staged)
            files = [p for p in (a.paths and list(iter_files(a.paths, cfg)) or only) if p in only]
            files = [p for p in files if os.path.splitext(p)[1].lower() in ALL_EXT and not _ignored(p, cfg)]
        else:
            if not a.paths:
                ap.print_help()
                return 2
            files = list(iter_files(a.paths, cfg))
        fixed_files = 0
        for p in files:
            try:
                text = open(p, encoding='utf-8').read()
            except (UnicodeDecodeError, OSError):
                continue
            found, edits = lint_file(linter, p, text, only.get(p) if only is not None else None)
            if a.fix and edits:
                new = text
                for _ in range(3):                     # виправлення можуть відкрити наступні
                    new2 = apply_edits(new, edits)
                    if new2 == new:
                        break
                    new = new2
                    found, edits = lint_file(linter, p, new, only.get(p) if only is not None else None)
                    edits = [e for e in edits]
                if new != text:
                    open(p, 'w', encoding='utf-8').write(new)
                    fixed_files += 1
            issues += [i for i in found if LEVELS[i.level] >= minlvl]
        if a.fix and a.format == 'text':
            print(f'Виправлено файлів: {fixed_files}.' if fixed_files else 'Нічого виправляти автоматично.')

    if a.format == 'json':
        print(json.dumps([i.as_dict() for i in issues], ensure_ascii=False, indent=2))
    elif a.format == 'github':
        report_github(issues)
    else:
        report_text(issues, by_id, a.verbose, color, not a.fix)
    bad = any(i.level == 'error' for i in issues) or (a.strict and any(i.level == 'warning' for i in issues))
    return 1 if bad else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(0)
