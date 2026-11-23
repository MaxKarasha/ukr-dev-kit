"""Режисерська розмітка ukr-voice і її переклад для Gemini TTS. Лише стандартна бібліотека.

Одна розмітка для обох рушіїв:
    (радісно) …        емоція з цього місця до кінця репліки чи до наступної емоції
    /  //  ///         пауза: коротка / середня / довга;  [0.6] — пауза в секундах
    *слово*            логічний наголос фрази (виділення)
    О~го               протягнути голосну
    {швидко: …}        особлива подача шматка: швидко, повільно, тихо, голосно, високо, низько, рівно, жваво
    за+мок             ручний наголос: «+» після наголошеної голосної

HolosTTS виконує її сам (holos_engine.py). Для Gemini текст розбивається на частини з описом подачі
(speechMetadata.style), паузи стають тегами [short pause]/[pause]/[long pause], «+» — знаком наголосу U+0301.
"""
from __future__ import annotations

import json
import os
import re

EMOTIONS = ['спокійно', 'радісно', 'захоплено', 'здивовано', 'обурено', 'таємниче', 'сумно', 'задумливо',
            'гордо', 'налякано', 'хитро']
ALIASES = {'весело': 'радісно', 'сердито': 'обурено', 'злякано': 'налякано', 'пошепки': 'таємниче'}
SPANS = ['швидко', 'повільно', 'тихо', 'голосно', 'високо', 'низько', 'рівно', 'жваво']

EMO_STYLE = {
    'спокійно': 'calm, even',
    'радісно': 'joyful, smiling, warm',
    'захоплено': 'excited, enthusiastic, energetic',
    'здивовано': 'surprised, amazed',
    'обурено': 'indignant, annoyed',
    'таємниче': 'mysterious, hushed, almost whispering',
    'сумно': 'sad, soft, slower',
    'задумливо': 'thoughtful, pensive, unhurried',
    'гордо': 'proud, confident',
    'налякано': 'frightened, tense, breathless',
    'хитро': 'sly, playful, conspiratorial',
}
SPAN_STYLE = {'швидко': 'faster pace', 'повільно': 'slower pace', 'тихо': 'quietly', 'голосно': 'loudly',
              'високо': 'higher pitch', 'низько': 'lower pitch', 'рівно': 'flat, neutral intonation',
              'жваво': 'lively, animated'}
VOWELS = 'аеєиіїоуюяАЕЄИІЇОУЮЯ'
ACUTE = '́'

_TOKEN = re.compile(r'\((?P<emo>[^()\s]+)\)|\[(?P<sec>\d+(?:[.,]\d+)?)\]|(?P<slash>/{1,3})|\{(?P<mods>[^:{}]+):'
                    r'|(?P<close>\})|(?P<star>\*)|(?P<ch>.)', re.S)


def apply_lexicon(text: str, path: str) -> str:
    """Словник вимови {"Ніко": "Ніко+"} — імена й слова з незвичним наголосом."""
    if not path or not os.path.exists(path):
        return text
    try:
        lex = json.load(open(path, encoding='utf-8'))
    except (OSError, ValueError):
        return text
    for w, r in lex.items():
        text = re.sub(r'(?<![\w+])' + re.escape(w) + r'(?![\w+])', r, text)
    return text


def emotion(name: str):
    n = ALIASES.get(name.lower(), name.lower())
    return n if n in EMO_STYLE else None


def _pause_tag(sec: float) -> str:
    return '[short pause]' if sec < 0.2 else '[pause]' if sec < 0.45 else '[long pause]'


def to_gemini(text: str) -> list:
    """Розмічений текст → [(текст, [описи подачі])] для частин запиту Gemini."""
    parts, buf = [], ''
    emo, mods, emph_words, cur_emph, in_emph = None, [], [], '', False

    def style():
        s = []
        if emo:
            s.append(EMO_STYLE[emo])
        s += [SPAN_STYLE[m] for m in mods]
        if emph_words:
            s.append('stress the words: ' + ', '.join(f'«{w}»' for w in emph_words))
        return s

    def flush():
        nonlocal buf, emph_words
        if buf.strip():
            parts.append((re.sub(r'\s+', ' ', buf).strip(), style()))
        buf, emph_words = '', []

    for m in _TOKEN.finditer(text):
        g = m.lastgroup
        if g == 'emo':
            e = emotion(m['emo'])
            if e is None:                       # звичайні дужки в тексті — лишаємо як є
                buf += m.group()
                continue
            flush()
            emo = e
        elif g == 'sec':
            buf += ' ' + _pause_tag(float(m['sec'].replace(',', '.'))) + ' '
        elif g == 'slash':
            buf += ' ' + ['[short pause]', '[pause]', '[long pause]'][len(m['slash']) - 1] + ' '
        elif g == 'mods':
            ms = [x for x in m['mods'].lower().split() if x in SPAN_STYLE]
            if not ms:
                buf += m.group()
                continue
            flush()
            mods = ms
        elif g == 'close':
            if mods:
                flush()
                mods = []
            else:
                buf += '}'
        elif g == 'star':
            if in_emph:
                emph_words.append(cur_emph.strip().replace('+', ''))
                cur_emph = ''
            in_emph = not in_emph
        else:
            ch = m['ch']
            if ch == '~':
                continue
            if ch == '+' and buf and buf[-1] in VOWELS:
                ch = ACUTE
            buf += ch
            if in_emph:
                cur_emph += m['ch']
    flush()
    # сусідні частини з однаковою подачею — разом
    merged = []
    for t, s in parts:
        if merged and merged[-1][1] == s:
            merged[-1] = (merged[-1][0] + ' ' + t, s)
        else:
            merged.append((t, s))
    return merged


def plain(text: str) -> str:
    """Текст без розмітки — для субтитрів і перевірки розбірливості."""
    t = re.sub(r'\((?:' + '|'.join(EMOTIONS + list(ALIASES)) + r')\)', ' ', text, flags=re.I)
    t = re.sub(r'\[\d+(?:[.,]\d+)?\]|/{1,3}', ' ', t)
    t = re.sub(r'\{(?:[^:{}]+):', '', t).replace('}', '')
    t = t.replace('*', '').replace('~', '').replace('+', '')
    return re.sub(r'\s+', ' ', t).strip()


def split_sentences(text: str, limit: int) -> list:
    """Ріже довгий текст на шматки до limit символів по межах речень (для довгих запитів)."""
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ''
    for sent in re.split(r'(?<=[.!?…])\s+', text):
        if cur and len(cur) + len(sent) + 1 > limit:
            chunks.append(cur)
            cur = sent
        else:
            cur = f'{cur} {sent}'.strip()
    if cur:
        chunks.append(cur)
    return chunks
