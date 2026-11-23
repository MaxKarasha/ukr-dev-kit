"""Субтитри SRT/VTT до озвучки. Лише стандартна бібліотека.

Текст субтитрів — завжди оригінальний (без помилок розпізнавання). Час кожного слова береться з
whisper.cpp (мітки на рівні слів) і накладається на оригінал вирівнюванням difflib; слова, яких
Whisper не почув, отримують час інтерполяцією. Без Whisper — пропорційно довжині слів.

Розбиття на титри за звичними правилами: до 42 символів у рядку, до 2 рядків, до 6 с на титр,
межа — кінець речення, зміна мовця або довга пауза.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional


@dataclass
class Word:
    text: str
    speaker: str = ''
    start: float = -1.0
    end: float = -1.0


def _norm(w: str) -> str:
    w = w.lower().replace('́', '')
    w = re.sub("[ʼ’'`]", '', w)
    return re.sub(r'[^\w]', '', w)


def words_from(lines: list) -> list:
    """lines: [(мовець, текст без розмітки)] → [Word]."""
    out = []
    for speaker, text in lines:
        for w in text.split():
            out.append(Word(w, speaker))
    return out


def whisper_words(audio: str, exe: str, model: str) -> list:
    """[(початок, кінець, слово)] у секундах з whisper.cpp (-ml 1 -sow: по слову на сегмент)."""
    tmp = tempfile.mkdtemp(prefix='ukr-subs-')
    wav = os.path.join(tmp, 'a.wav')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', audio, '-ar', '16000', '-ac', '1', wav], check=True)
    subprocess.run([exe, '-m', model, '-l', 'uk', '-ml', '1', '-sow', '-oj', '-of', os.path.join(tmp, 'w'), '-f', wav],
                   check=True, capture_output=True)
    data = json.load(open(os.path.join(tmp, 'w.json'), encoding='utf-8'))
    res = []
    for seg in data.get('transcription', []):
        t = seg.get('text', '').strip()
        if t:
            res.append((seg['offsets']['from'] / 1000, seg['offsets']['to'] / 1000, t))
    return res


def align(words: list, heard: list) -> None:
    """Проставляє start/end кожному Word за мітками Whisper; решту — інтерполяцією."""
    a = [_norm(w.text) for w in words]
    b = [_norm(h[2]) for h in heard]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal' or (op == 'replace' and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):                 # однакова кількість слів — зіставляємо поштучно
                words[i1 + k].start, words[i1 + k].end = heard[j1 + k][0], heard[j1 + k][1]
        elif op == 'replace' and j2 > j1:           # кілька слів проти кількох — ділимо проміжок
            s, e = heard[j1][0], heard[j2 - 1][1]
            _spread(words[i1:i2], s, e)
    _interpolate(words)


def _spread(ws: list, start: float, end: float) -> None:
    total = sum(len(w.text) for w in ws) or 1
    t = start
    for w in ws:
        d = (end - start) * len(w.text) / total
        w.start, w.end = t, t + d
        t += d


def _interpolate(words: list) -> None:
    n = len(words)
    i = 0
    while i < n:
        if words[i].start >= 0:
            i += 1
            continue
        j = i
        while j < n and words[j].start < 0:
            j += 1
        left = words[i - 1].end if i > 0 else 0.0
        right = words[j].start if j < n else left + 0.35 * (j - i)
        _spread(words[i:j], left, max(right, left + 0.05 * (j - i)))
        i = j


def proportional(words: list, duration: float) -> None:
    """Без Whisper: час пропорційно довжині слів, з короткими паузами після речень."""
    weights = [len(w.text) + (6 if re.search(r'[.!?…]$', w.text) else 2 if w.text.endswith(',') else 0)
               for w in words]
    total = sum(weights) or 1
    t = 0.0
    for w, k in zip(words, weights):
        d = duration * k / total
        w.start, w.end = t, t + d * len(w.text) / k if k else t + d
        t += d


@dataclass
class Cue:
    start: float
    end: float
    text: str
    speaker: str = ''


def build_cues(words: list, max_chars: int = 42, max_lines: int = 2, max_dur: float = 6.0,
               gap: float = 0.7) -> list:
    cues, cur = [], []

    def flush():
        if cur:
            cues.append(Cue(cur[0].start, cur[-1].end, _wrap(' '.join(w.text for w in cur), max_chars),
                            cur[0].speaker))
            cur.clear()

    for w in words:
        if cur:
            text = ' '.join(x.text for x in cur + [w])
            too_long = len(text) > max_chars * max_lines or w.end - cur[0].start > max_dur
            if w.speaker != cur[-1].speaker or w.start - cur[-1].end > gap or too_long:
                flush()
        cur.append(w)
        if re.search(r'[.!?…]["»)]*$', w.text) and len(' '.join(x.text for x in cur)) > max_chars * 0.5:
            flush()
    flush()
    for a, b in zip(cues, cues[1:]):                 # титри не перекриваються
        if a.end > b.start:
            a.end = b.start
    return cues


def _wrap(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    words = text.split()
    best, best_score = text, 10 ** 9
    for k in range(1, len(words)):
        l1, l2 = ' '.join(words[:k]), ' '.join(words[k:])
        if len(l1) > width or len(l2) > width:
            continue
        score = abs(len(l1) - len(l2)) - (8 if re.search(r'[,.;:!?—]$', l1) else 0)
        if score < best_score:
            best, best_score = f'{l1}\n{l2}', score
    return best


def _ts(t: float, sep: str) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}'


def to_srt(cues: list, speakers: bool = False) -> str:
    out = []
    for n, c in enumerate(cues, 1):
        text = f'{c.speaker}: {c.text}' if speakers and c.speaker else c.text
        out.append(f'{n}\n{_ts(c.start, ",")} --> {_ts(c.end, ",")}\n{text}\n')
    return '\n'.join(out)


def to_vtt(cues: list, speakers: bool = False) -> str:
    out = ['WEBVTT', '']
    for c in cues:
        text = f'<v {c.speaker}>{c.text}' if speakers and c.speaker else c.text
        out.append(f'{_ts(c.start, ".")} --> {_ts(c.end, ".")}\n{text}\n')
    return '\n'.join(out)


def make(audio: str, lines: list, out_base: str, formats: tuple = ('srt', 'vtt'), whisper: Optional[tuple] = None,
         duration: float = 0.0, max_chars: int = 42) -> tuple:
    """Створює файли субтитрів. Повертає (шляхи, метод: 'whisper' | 'пропорційно')."""
    words = words_from(lines)
    if not words:
        return [], ''
    method = 'пропорційно'
    if whisper and all(whisper):
        try:
            heard = whisper_words(audio, *whisper)
            if heard:
                align(words, heard)
                method = 'whisper'
        except (OSError, subprocess.CalledProcessError, ValueError):
            pass
    if method != 'whisper':
        proportional(words, duration)
    cues = build_cues(words, max_chars=max_chars)
    speakers = len({w.speaker for w in words}) > 1
    paths = []
    for f in formats:
        p = f'{out_base}.{f}'
        open(p, 'w', encoding='utf-8').write(to_srt(cues, speakers) if f == 'srt' else to_vtt(cues, speakers))
        paths.append(p)
    return paths, method
