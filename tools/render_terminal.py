#!/usr/bin/env python3
"""Запускає команду й малює її кольоровий вивід як SVG-«скриншот» термінала для README.

    python3 tools/render_terminal.py docs/assets/lint-demo.svg -- python3 skills/ukr-proofread/scripts/ukr_lint.py docs/demo/uk.json
"""
import html
import os
import re
import subprocess
import sys

COLORS = {'31': '#ff7b72', '32': '#3fb950', '33': '#e3b341', '36': '#56d4dd', '2': '#8b949e'}
FG, BG, BAR = '#e6edf3', '#0d1117', '#161b22'
CH, LH, PAD, TOP = 8.6, 21, 22, 46


def parse(line):
    """ANSI-рядок → [(текст, {color, bold, underline, dim})]."""
    out, style = [], {}
    pos = 0
    for m in re.finditer(r'\x1b\[([\d;]*)m', line):
        if m.start() > pos:
            out.append((line[pos:m.start()], dict(style)))
        for code in (m.group(1) or '0').split(';'):
            if code == '0':
                style = {}
            elif code == '1':
                style['bold'] = True
            elif code == '4':
                style['underline'] = True
            elif code in COLORS:
                style['color'] = COLORS[code]
        pos = m.end()
    if pos < len(line):
        out.append((line[pos:], dict(style)))
    return out


def main():
    out, cmd = sys.argv[1], sys.argv[sys.argv.index('--') + 1:]
    prompt = '$ ' + ' '.join(c if ' ' not in c else f'"{c}"' for c in cmd).replace(sys.executable, 'python3')
    prompt = prompt.replace('python3 skills/ukr-proofread/scripts/ukr_lint.py', 'ukr-lint') \
                   .replace('python3 skills/ukr-i18n/scripts/i18n_check.py', 'ukr-i18n') \
                   .replace('python3 skills/ukr-data/scripts/ukr_data.py', 'ukr-data')
    r = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, FORCE_COLOR='1', NO_COLOR=''))
    lines = [f'\x1b[32m{prompt[:2]}\x1b[0m\x1b[1m{prompt[2:]}\x1b[0m'] + r.stdout.rstrip('\n').split('\n')
    width = int(max(len(re.sub(r'\x1b\[[\d;]*m', '', l)) for l in lines) * CH + PAD * 2)
    height = TOP + len(lines) * LH + PAD
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           f'<rect width="{width}" height="{height}" rx="12" fill="{BG}"/>',
           f'<rect width="{width}" height="34" rx="12" fill="{BAR}"/><rect y="22" width="{width}" height="12" fill="{BAR}"/>',
           '<circle cx="22" cy="17" r="6" fill="#ff5f57"/><circle cx="42" cy="17" r="6" fill="#febc2e"/>'
           '<circle cx="62" cy="17" r="6" fill="#28c840"/>',
           f'<g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, \'Liberation Mono\', monospace" '
           f'font-size="14" fill="{FG}" xml:space="preserve">']
    for i, line in enumerate(lines):
        y = TOP + 14 + i * LH
        spans = []
        for text, st in parse(line):
            attrs = ''
            if 'color' in st:
                attrs += f' fill="{st["color"]}"'
            if st.get('bold'):
                attrs += ' font-weight="700"'
            if st.get('underline'):
                attrs += ' text-decoration="underline"'
            spans.append(f'<tspan{attrs}>{html.escape(text)}</tspan>')
        svg.append(f'<text x="{PAD}" y="{y}">{"".join(spans)}</text>')
    svg.append('</g></svg>')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, 'w', encoding='utf-8').write('\n'.join(svg) + '\n')
    print(f'✓ {out} ({width}×{height})')


if __name__ == '__main__':
    main()
