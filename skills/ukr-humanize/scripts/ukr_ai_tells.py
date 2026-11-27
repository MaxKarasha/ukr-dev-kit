#!/usr/bin/env python3
"""ukr-ai-tells — знаходить у тексті ознаки ШІ-стилю: словникові штампи (rules/tells.txt) і структурні
звички (тире-звʼязки, Title Case у заголовках, жирні мітки в списках, однакові початки речень,
рівна довжина речень, трійки). Рахує щільність на 1000 слів.

Сканер лише підказує, де дивитися. Окремий збіг нічого не доводить — важить купа ознак.

    ukr_ai_tells.py post.md docs/            # файли й теки (.md .txt .rst .mdx)
    ukr_ai_tells.py -t "текст"               # шматок тексту
    cat draft.md | ukr_ai_tells.py --stdin
    ukr_ai_tells.py post.md --format json    # для обробки
    ukr_ai_tells.py post.md --max-score 10   # код виходу 1, якщо щільність вища (CI)

Приклади штампів у документації про стиль виключай коментарем: ukr-ai-tells-disable … ukr-ai-tells-enable,
ukr-ai-tells-disable-line, ukr-ai-tells-disable-next-line (у Markdown — <!-- … -->).

Лише стандартний Python 3.10+.
"""
import argparse
import json
import os
import re
import statistics
import sys
from dataclasses import asdict, dataclass

__version__ = '0.4.1'

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_FILE = os.path.join(os.path.dirname(HERE), 'rules', 'tells.txt')

WEIGHT = {'strong': 3.0, 'medium': 1.5, 'weak': 0.5}
STRENGTH_UK = {'strong': 'сильна', 'medium': 'середня', 'weak': 'слабка'}
APOS = "ʼ’'‘`"
# Межі слова — лише якщо шаблон починається / закінчується літерою. Шаблон, що починається з коми чи «^»
# (дієприслівниковий хвіст, «. Крім того»), межі не потребує.
LB = f"(?:(?<![\\w{APOS}-])(?=\\w)|(?=\\W))"
RB = f"(?:(?<=\\w)(?![\\w{APOS}])|(?<=\\W))"
TEXT_EXT = {'.md', '.markdown', '.mdx', '.txt', '.rst'}
SKIP_DIRS = {'.git', 'node_modules', 'dist', 'build', 'vendor', '.venv', 'venv', '__pycache__'}

EMOJI = re.compile('[\U0001F300-\U0001FAFF☀-➿⭐✅❌✨]')
HEADING = re.compile(r'^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$')
LIST_ITEM = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s+')
BOLD_LABEL = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s+\*\*[^*]{1,60}?:?\*\*\s*:?')
HR = re.compile(r'^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$')
WORD = re.compile(f"[A-Za-zА-Яа-яІіЇїЄєҐґ{APOS}-]+")  # ukr-lint-disable-line
CYR_WORD = re.compile(f"[А-ЯІЇЄҐ][а-яіїєґ{APOS}-]+")
SENT_END = re.compile(r'(?<=[.!?…])\s+(?=[«"(\[]?[A-ZА-ЯІЇЄҐ0-9])')  # ukr-lint-disable-line
DASH = re.compile(r'\s[—–]\s')
# тире-звʼязка: після тире йде сполучник («— і що з цього вийшло», «— тепер відповіді в Redis»).
# «X — це Y» не рахуємо: це звичайне граматичне тире; «не X — це Y» ловить §1.
CONNECTOR_DASH = re.compile(r"\s[—–]\s(?:і|й|а|але|та|бо|адже|ось|саме|навіть|завдяки|тобто|причому|тепер|отже|тож|зате|втім|проте|натомість|просто|ніяких|жодних)\s", re.I)
MIN_WORDS = 300   # коротші тексти рахуються як 300 слів, щоб одна знахідка не давала «сильний ШІ-стиль»
TRIAD = re.compile(r"(?<![\w,])([\w'ʼ’-]+(?:\s[\w'ʼ’-]+)?),\s([\w'ʼ’-]+(?:\s[\w'ʼ’-]+)?),?\s(?:і|й|та|and)\s([\w'ʼ’-]+(?:\s[\w'ʼ’-]+)?)(?=[.!?,;]|$)")
CONCLUSION_HEADINGS = re.compile(
    r'^(?:висновк?и?|висновок|підсумок|підсумки|на\s+завершення|заключення|ключові\s+(?:переваги|висновки|моменти)|'
    r'виклики\s+(?:та|і)\s+перспективи|майбутні\s+перспективи|погляд\s+у\s+майбутнє|попри\s+виклики)$', re.I)


@dataclass
class Rule:
    key: str
    strength: str
    rx: re.Pattern
    section: str
    explanation: str


@dataclass
class Finding:
    path: str
    line: int
    key: str
    strength: str
    section: str
    match: str
    explanation: str
    span: tuple = (-1, -1)


def load_rules(path=RULES_FILE):
    rules, seen = [], set()
    for n, line in enumerate(open(path, encoding='utf-8'), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = [p.strip() for p in line.split(' | ')]
        if len(parts) != 5:
            raise SystemExit(f'{path}:{n}: очікую 5 полів через « | », маю {len(parts)}')
        key, strength, pattern, section, explanation = parts
        if strength not in WEIGHT:
            raise SystemExit(f'{path}:{n}: невідома сила «{strength}»')
        if key in seen:
            raise SystemExit(f'{path}:{n}: правило {key} уже є')
        seen.add(key)
        body = pattern.replace(' ', r'\s+')
        try:
            rx = re.compile(f'{LB}(?:{body}){RB}', re.I | re.M)
        except re.error as e:
            raise SystemExit(f'{path}:{n}: поганий шаблон: {e}')
        rules.append(Rule(key, strength, rx, section, explanation))
    return rules


def prose_lines(text):
    """Рядки прози: без frontmatter, блоків коду, рядкового коду, адрес посилань. Номери рядків зберігаються."""
    lines = text.split('\n')
    out = []
    in_code = False
    off = skip_next = False
    fm = bool(lines) and lines[0].strip() == '---'
    for i, raw in enumerate(lines):
        # директиви в будь-якому коментарі: ukr-ai-tells-disable … ukr-ai-tells-enable, -disable-line, -disable-next-line
        if 'ukr-ai-tells-' in raw:
            if 'ukr-ai-tells-disable-next-line' in raw:
                skip_next = True
            elif 'ukr-ai-tells-disable-line' in raw:
                out.append('')
                continue
            elif 'ukr-ai-tells-disable' in raw:
                off = True
            elif 'ukr-ai-tells-enable' in raw:
                off = False
            out.append('')
            continue
        if off or skip_next:
            skip_next = False
            out.append('')
            continue
        if fm:
            out.append('')
            if i > 0 and raw.strip() == '---':
                fm = False
            continue
        if re.match(r'^\s*(```|~~~)', raw):
            in_code = not in_code
            out.append('')
            continue
        if in_code or raw.startswith('    ') and not LIST_ITEM.match(raw) or re.match(r'^\s*</?[a-zA-Z!]', raw):
            out.append('')
            continue
        s = re.sub(r'`[^`]*`', ' ', raw)
        s = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', s)       # посилання й картинки → лише текст
        s = re.sub(r'https?://\S+', ' ', s)
        out.append(s)
    return out


def paragraphs(lines):
    """[(перший_рядок, текст, тип)] — тип: heading | list | hr | para."""
    blocks, buf, start = [], [], 0
    for i, s in enumerate(lines):
        if not s.strip():
            if buf:
                blocks.append((start, ' '.join(buf), 'para'))
                buf = []
            continue
        if HEADING.match(s) or HR.match(s) or LIST_ITEM.match(s):
            if buf:
                blocks.append((start, ' '.join(buf), 'para'))
                buf = []
            kind = 'heading' if HEADING.match(s) else 'hr' if HR.match(s) else 'list'
            blocks.append((i, s, kind))
            continue
        if not buf:
            start = i
        buf.append(s.strip())
    if buf:
        blocks.append((start, ' '.join(buf), 'para'))
    return blocks


def sentences(text):
    text = re.sub(r'\*\*|__', '', text)
    return [s.strip() for s in SENT_END.split(text) if WORD.search(s)]


PLACEHOLDER = re.compile(r"\[(?:[А-ЯІЇЄҐ]|[A-Z])[^\[\]\n]{1,28}\](?!\()|\[[а-яіїєґ][а-яіїєґʼ’' ]{1,28}\](?!\()")  # ukr-lint-disable-line
LABEL_DASH = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s+(?:\*\*[^*]{1,50}\*\*|[^—–:]{1,40}?)\s[—–]\s\S')
HYPHEN_AS_DASH = re.compile(r'[а-яіїєґ,] - [а-яіїєґ]', re.I)
LATIN_IN_CYR = re.compile(r'(?=\w*[А-Яа-яІіЇїЄєҐґ])(?=\w*[a-zA-Z])\b\w+\b')
PLAIN_CHANNELS = {'email', 'sms', 'instagram', 'facebook', 'linkedin', 'plain', 'messenger'}


def scan(text, path='<текст>', rules=None, channel='markdown'):
    rules = rules if rules is not None else load_rules()
    lines = prose_lines(text)
    findings = []

    def add(line, key, strength, section, match, expl, span=(-1, -1)):
        findings.append(Finding(path, line + 1, key, strength, section, match.strip()[:80], expl, span))

    # ── словник ──
    joined = '\n'.join(lines)
    offsets = [0]
    for s in lines:
        offsets.append(offsets[-1] + len(s) + 1)

    def line_of(pos):
        lo, hi = 0, len(offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if offsets[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo

    for r in rules:
        for m in r.rx.finditer(joined):
            add(line_of(m.start()), r.key, r.strength, r.section, m.group(0).replace('\n', ' '), r.explanation,
                (m.start(), m.end()))
    # один збіг — одна ознака: правила того самого § не рахуємо двічі на тому самому місці
    kept = []
    for f in sorted(findings, key=lambda f: (-WEIGHT[f.strength], f.span[0])):
        if any(k.section == f.section and k.span[0] < f.span[1] and f.span[0] < k.span[1] for k in kept):
            continue
        kept.append(f)
    findings[:] = kept

    blocks = paragraphs(lines)
    prose = [b for b in blocks if b[2] in ('para', 'list')]
    words = sum(len(WORD.findall(b[1])) for b in blocks if b[2] != 'hr')

    # ── заголовки: Title Case, емодзі, «Висновок» ──
    emoji_heads = []
    for ln, s, kind in blocks:
        if kind != 'heading':
            continue
        title = HEADING.match(s).group(2)
        bare = EMOJI.sub('', re.sub(r'[*_]', '', title)).strip()
        ws = WORD.findall(re.sub(r'\([^)]*\)', ' ', bare))          # без дужок: там зазвичай імена й абревіатури
        caps = [w for w in ws[1:] if CYR_WORD.fullmatch(w)]
        if len(ws) >= 4 and len(caps) >= 2 and len(caps) >= (len(ws) - 1) * 0.6:
            add(ln, 'title-case', 'weak', '20', title,
                'Title Case — англійська звичка, але у 2026 частіше людська (SEO, переклад), ніж ШІ. Виправ як стиль: '
                'з великої лише перше слово й власні назви.')
        if EMOJI.search(title):
            emoji_heads.append((ln, title))
        if CONCLUSION_HEADINGS.match(bare.strip(' :.')):
            add(ln, 'conclusion-heading', 'strong' if re.match(r'(?i)висно|підсум', bare.strip()) else 'medium', '13', title,
                f'Шаблонний розділ «{bare.strip()}» (як «Висновок», «Ключові переваги», «Виклики та перспективи»). '
                'Підсумок, що повторює текст, прибери; закінчи останнім фактом. Перелік переваг дай змістовим заголовком.')

    # ── списки: жирні мітки, емодзі ──
    if emoji_heads:
        add(emoji_heads[0][0], 'emoji-heading', 'medium' if len(emoji_heads) > 1 else 'weak', '20', emoji_heads[0][1],
            f'Емодзі в заголовках ({len(emoji_heads)}) як прикраса.')
    runs, run = [], []
    for ln, s, kind in blocks + [(-1, '', 'end')]:
        if kind == 'list' and BOLD_LABEL.match(s):
            run.append(ln)
            continue
        if len(run) >= 2:
            runs.append(run)
        run = []
    if runs:
        items = sum(len(r) for r in runs)
        add(runs[0][0], 'bold-labels', 'medium' if any(len(r) >= 3 for r in runs) else 'weak', '19', lines[runs[0][0]],
            f'{items} пунктів у {len(runs)} списках з жирною міткою «**Мітка:** текст». '
            'Якщо мітки нічого не додають — перепиши прозою. У довідниках це нормально.')
    emoji_items = [ln for ln, s, kind in blocks if kind == 'list' and EMOJI.search(s[:12])]
    if len(emoji_items) >= 2:
        add(emoji_items[0], 'emoji-list', 'medium', '20', lines[emoji_items[0]],
            f'Емодзі на початку {len(emoji_items)} пунктів списку як прикраса.')

    hrs = [b for b in blocks if b[2] == 'hr']
    if len(hrs) >= 2:
        add(hrs[0][0], 'horizontal-rules', 'weak', '20', '---', f'{len(hrs)} горизонтальні лінії між розділами.')

    # ── тире-звʼязки ──
    conn = [(ln, m) for ln, s, k in prose for snt in sentences(s) for m in CONNECTOR_DASH.finditer(snt)]
    if len(conn) >= 2:
        add(conn[0][0], 'connector-dash', 'medium' if len(conn) >= 3 else 'weak', '8',
            ', '.join(f'р. {ln + 1} «{m.group(0).strip()}»' for ln, m in conn[:6]),
            f'{len(conn)} тире-звʼязки («… — і що з цього вийшло», «… — тепер …»). Граматичне тире («Київ — столиця», '
            'пропущене дієслово) лиши, а звʼязку заміни крапкою, комою чи двокрапкою.')

    # ── речення: однакові початки, рівна довжина, трійки ──
    all_sents = []
    for ln, s, kind in prose:
        if kind == 'para':
            for snt in sentences(s):
                all_sents.append((ln, snt))
    prev, streak, streak_ln = None, 0, 0
    for ln, snt in all_sents + [(0, '')]:
        first = (WORD.findall(snt) or [''])[0].lower()
        if first and first == prev:
            streak += 1
        else:
            if streak >= 4 or streak == 3 and len(prev) > 3:
                add(streak_ln, 'same-opening', 'medium' if streak >= 4 else 'weak', '7', prev,
                    f'{streak} речення поспіль починаються з «{prev}». Об\'єднай або почни з дії.')
            prev, streak, streak_ln = first, 1, ln
    lens = [len(WORD.findall(snt)) for _, snt in all_sents]
    if len(lens) >= 8:
        cv = statistics.pstdev(lens) / statistics.mean(lens)
        if cv < 0.45:                       # у людей ≈ 0,65, у GPT-4o / Llama ≈ 0,40–0,44 (корпус HAP-E)
            add(all_sents[0][0], 'uniform-length', 'weak', '7', f'{len(lens)} речень, у середньому {statistics.mean(lens):.0f} слів, варіація {cv:.2f}',
                'Речення майже однакової довжини по всьому тексту. Живий текст чергує короткі й довгі.')
    para_lens = [len(WORD.findall(s)) for ln, s, k in prose if k == 'para']
    if len(para_lens) >= 5 and statistics.mean(para_lens) > 15:
        pcv = statistics.pstdev(para_lens) / statistics.mean(para_lens)
        if pcv < 0.3:
            add(prose[0][0], 'uniform-paragraphs', 'weak', '7', f'{len(para_lens)} абзаців, варіація {pcv:.2f}',
                'Абзаци майже однакової довжини. Не нав\'язуй квот, але один-два довші чи коротші абзаци — норма людського тексту.')

    # ── тире: щільність на речення й тире-зʼєднувач після назви пункту ──
    sent_total = len(all_sents)
    dash_sents = sum(1 for _, snt in all_sents if DASH.search(f' {snt} '))
    if sent_total >= 8 and dash_sents / sent_total > 0.25:
        add(all_sents[0][0], 'dash-rate', 'medium', '8', f'тире в {dash_sents} з {sent_total} речень',
            f'Тире в {dash_sents * 100 // sent_total} реченнях зі 100. У людей ≈ 9, у Claude ≈ 24 (вимір panchlab/humanizer-uk). '
            'Спершу зніми тире-зʼєднувачі, з граматичних лиши потрібні, решту речень перебудуй. Діалоги й діапазони не рахуються.')
    labels = [ln for ln, s, k in blocks if k == 'list' and LABEL_DASH.match(s)]
    if len(labels) >= 2:
        add(labels[0], 'label-dash', 'strong' if len(labels) >= 3 else 'medium', '8', lines[labels[0]],
            f'{len(labels)} пунктів «Назва — пояснення». Таке тире — зʼєднувач: у Claude це ≈ 45 % усіх тире, у людей до 1 %. '
            'Заміни на двокрапку, крапку або перепиши пункт реченням.')

    # ── розмітка чату й заглушки ──
    raw = text.split('\n')
    holders = [(i, m.group(0)) for i, l in enumerate(lines) for m in PLACEHOLDER.finditer(l)]
    if holders:
        add(holders[0][0], 'placeholder', 'strong', '22', ', '.join(h for _, h in holders[:4]),
            f'Заглушки ({len(holders)}): місця для фактів автора. У готовому тексті заміни фактом або винеси в питання автору.')
    if channel in PLAIN_CHANNELS:
        md = [(i, l) for i, l in enumerate(lines) if '**' in l or HEADING.match(l) or HR.match(raw[i] if i < len(raw) else '')]
        if md:
            add(md[0][0], 'markup-in-plain', 'strong', '19', md[0][1],
                f'Розмітка Markdown ({len(md)} рядків) у каналі «{channel}», який її не показує: зірочки й решітки побачить читач. '
                'Прибери символи, структуру (абзаци, порядок) лиши.')
    excl = sum(s.count('!') for ln, s, k in prose)
    if words >= 150 and excl >= 3 and excl * 1000 / words > 8:
        add(prose[0][0], 'exclamations', 'weak', '16', f'{excl} знаків оклику на {words} слів',
            f'{excl * 1000 / words:.0f} знаків оклику на 1000 слів (у Claude в постах ≈ 11–15, у людській рекламі ≈ 2–6).')

    triads = [(ln, m.group(0)) for ln, s, k in prose for m in TRIAD.finditer(re.sub(r'\*\*', '', s))]
    if words and len(triads) >= 3 and len(triads) * 1000 / words >= 6:
        add(triads[0][0], 'triads', 'weak', '6', '; '.join(t for _, t in triads[:3]),
            f'{len(triads)} переліки по три. Перевір, чи в кожному справді три окремі думки.')

    # ── одно-реченнєві «закриття» розділу ──
    for idx, (ln, s, kind) in enumerate(blocks):
        if kind != 'para' or idx == 0:
            continue
        nxt = blocks[idx + 1][2] if idx + 1 < len(blocks) else 'end'
        prv = blocks[idx - 1]
        sn = sentences(s)
        if (len(sn) == 1 and len(WORD.findall(s)) <= 9 and nxt in ('heading', 'end', 'hr')
                and prv[2] == 'para' and len(WORD.findall(prv[1])) > 25):
            add(ln, 'one-line-closer', 'weak', '2', s,
                'Короткий абзац-«вирок» наприкінці розділу. Якщо він повторює попереднє — прибери.')

    # окреме слабке словникове слово нічого не означає: лишаємо його, лише якщо в тексті є інші ознаки
    rule_keys = {r.key for r in rules}
    others = [f for f in findings if not (f.strength == 'weak' and f.key in rule_keys)]
    if not others:
        findings = [f for f in findings if not (f.strength == 'weak' and f.key in rule_keys)]

    # ── ознаки людського тексту (не віднімаються від оцінки, але важать для рішення) ──
    human = []
    hy = sum(len(HYPHEN_AS_DASH.findall(s)) for ln, s, k in prose)
    if hy:
        human.append(f'дефіс замість тире ({hy})')
    lat = sum(len([w for w in LATIN_IN_CYR.findall(s) if re.search('[a-zA-Z]', w) and re.search('[а-яА-ЯіїєґІЇЄҐ]', w)])
              for ln, s, k in prose)
    if lat:
        human.append(f'латинські літери в кириличних словах ({lat})')
    aps = {c for c in "ʼ’'" if re.search(f'[а-яіїєґ]{c}[а-яіїєґ]', text, re.I)}
    if len(aps) > 1:
        human.append('різні апострофи')
    findings.sort(key=lambda f: (f.path, f.line))
    scan.human_signals = human
    return findings, words


def summarize(findings, words, human=None):
    score = sum(WEIGHT[f.strength] for f in findings)
    density = score * 1000 / max(words, MIN_WORDS)
    sections = sorted({f.section for f in findings}, key=lambda x: int(x) if x.isdigit() else 99)
    strong = sum(f.strength == 'strong' for f in findings)
    if density >= 30 and len(sections) >= 4:
        verdict = 'сильний ШІ-стиль — перепиши текст цілком, а не латай фрази'
    elif density >= 8 or strong >= 2 or strong and density >= 4:
        verdict = 'є ознаки ШІ-стилю — перепиши позначені місця'
    else:
        verdict = 'слідів ШІ-стилю майже немає'
    return {'words': words, 'findings': len(findings), 'score': round(score, 1),
            'density_per_1000': round(density, 1), 'sections': sections, 'verdict': verdict,
            'human_signals': human or []}


def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in sorted(files):
                    if os.path.splitext(f)[1].lower() in TEXT_EXT:
                        yield os.path.join(root, f)
        else:
            yield p


def color(s, code, on):
    return f'\033[{code}m{s}\033[0m' if on else s


def main(argv=None):
    ap = argparse.ArgumentParser(prog='ukr-ai-tells', description='Ознаки ШІ-стилю в українському тексті.')
    ap.add_argument('paths', nargs='*', help='файли або теки')
    ap.add_argument('-t', '--text', help='перевірити цей текст')
    ap.add_argument('--stdin', action='store_true', help='прочитати текст зі stdin')
    ap.add_argument('--format', choices=['text', 'json'], default='text')
    ap.add_argument('--min', choices=list(WEIGHT), default='weak', help='мінімальна сила для показу')
    ap.add_argument('--channel', default='markdown',
                    help='куди піде текст: markdown (сайт, документ, GitHub — типово), email, sms, instagram, '
                         'facebook, linkedin, messenger, plain. У «простих» каналах Markdown — помилка')
    ap.add_argument('--max-score', type=float, metavar='N', help='код виходу 1, якщо щільність на 1000 слів > N')
    ap.add_argument('--rules', default=RULES_FILE, help='інший файл словника')
    ap.add_argument('--no-color', action='store_true')
    ap.add_argument('--version', action='version', version=f'ukr-ai-tells {__version__}')
    a = ap.parse_args(argv)

    rules = load_rules(a.rules)
    docs = []
    if a.text is not None:
        docs.append(('<текст>', a.text))
    if a.stdin:
        docs.append(('<stdin>', sys.stdin.read()))
    for f in iter_files(a.paths):
        try:
            docs.append((f, open(f, encoding='utf-8').read()))
        except (OSError, UnicodeDecodeError) as e:
            print(f'✖ {f}: {e}', file=sys.stderr)
    if not docs:
        ap.print_help()
        return 2

    order = list(WEIGHT)
    cut = order.index(a.min)
    reports, worst = [], 0.0
    for path, text in docs:
        fs, words = scan(text, path, rules, a.channel)
        summ = summarize(fs, words, getattr(scan, 'human_signals', []))
        worst = max(worst, summ['density_per_1000'])
        shown = [f for f in fs if order.index(f.strength) <= cut]
        reports.append((path, shown, summ))

    if a.format == 'json':
        print(json.dumps([{'path': p, 'summary': s, 'findings': [{k: v for k, v in asdict(f).items() if k != 'span'}
                                                                    for f in fs]} for p, fs, s in reports],
                         ensure_ascii=False, indent=2))
    else:
        on = sys.stdout.isatty() and not a.no_color
        col = {'strong': '31', 'medium': '33', 'weak': '2'}
        for path, fs, s in reports:
            for f in fs:
                tag = color(f'[{STRENGTH_UK[f.strength]}] §{f.section} {f.key}', col[f.strength], on)
                print(f'{f.path}:{f.line}  {tag}  «{f.match}»\n    {f.explanation}')
            print(color(f'{path}: {s["words"]} слів, {s["findings"]} ознак, щільність {s["density_per_1000"]} '
                        f'на 1000 слів → {s["verdict"]}', '1', on))
            if s['human_signals']:
                print(f'    Ознаки людської чернетки: {", ".join(s["human_signals"])}. Це не ШІ: виправ форму знаків '
                      f'(ukr-proofread), слова не чіпай.')
    if a.max_score is not None and worst > a.max_score:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
