#!/usr/bin/env python3
"""ukr-voice — українська озвучка: Gemini TTS (хмара, найвища якість) або HolosTTS (локально, офлайн).

    ukr_voice.py doctor                          # що встановлено й який рушій буде використано
    ukr_voice.py setup gemini                    # зберегти ключ Gemini API (запитує у терміналі)
    ukr_voice.py setup holos                     # локальна модель HolosTTS (~2 ГБ, один раз)
    ukr_voice.py say "Привіт!" -o hi.mp3 [--preset оповідач] [--voice Kore] [--style "..."] [--engine gemini|holos]
    ukr_voice.py dialog scene.txt -o scene.mp3 [--cast "Оля=Zephyr,Тарас=Charon"] [--split dir/]
    ukr_voice.py batch jobs.json                 # [{"text", "out", "preset"|"voice", "style"?, "engine"?}]
    ukr_voice.py audition "Фраза" -o picks/ [--gender f|m] [--voices a,b]   # одна фраза різними голосами
    ukr_voice.py voices [--engine holos]  |  presets
    ukr_voice.py check hi.mp3 --text "Привіт!"   # розбірливість через Whisper (якщо встановлено)
    ukr_voice.py say "…" -o hi.mp3 --subs        # + субтитри hi.srt і hi.vtt (також для dialog)
    ukr_voice.py subs video.mp3 --text "…"       # субтитри до готового аудіо
    ukr_voice.py status | stop                   # локальний синтез: що запущено / зупинити

Рушій обирається сам (--engine auto): Gemini, якщо є ключ, інакше HolosTTS, якщо встановлено.
Формат файлу — за розширенням: .mp3 .wav .ogg .m4a .flac (усе, крім .wav, потребує ffmpeg).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import difflib
import getpass
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gemini_tts as G  # noqa: E402
import markup as M  # noqa: E402
import subtitles as SUBS  # noqa: E402

__version__ = '0.4.0'
DATA = os.environ.get('UKR_VOICE_HOME', os.path.expanduser('~/.local/share/ukr-voice'))
CONF = os.environ.get('UKR_VOICE_CONFIG', os.path.expanduser('~/.config/ukr-voice'))
CACHE = os.environ.get('UKR_VOICE_CACHE', os.path.expanduser('~/.cache/ukr-voice'))
VENV = os.path.join(DATA, 'venv')
VPY = os.path.join(VENV, 'Scripts' if os.name == 'nt' else 'bin', 'python')
HOLOS_DIR = os.path.join(DATA, 'HolosTTS')
PRESETS = os.path.join(CONF, 'presets.json')
LEXICON = os.path.join(CONF, 'lexicon.json')
CREDS = os.path.join(CONF, 'credentials')

# Закріплені версії: код HolosTTS і сумісна з ним ревізія ваг на Hugging Face.
HOLOS_REPO = 'https://github.com/patriotyk/HolosTTS.git'
HOLOS_COMMIT = '86c5b32cbb217ca030a15f8331f36ea9b85ff7d5'
HF_REVISION = '5d40fbaa99e55ebd3359a161bc86728ffdbd5c5f'
PIP = ['torch==2.14.1', 'torchaudio==2.11.0', 'transformers==5.20.2', 'scipy==1.13.1', 'numpy==2.2.6',
       'librosa==0.11.0', 'soundfile==0.14.0', 'huggingface_hub==2.3.0', 'stanza==1.15.0',
       'ukrainian-word-stress @ git+https://github.com/patriotyk/ukrainian-word-stress.git@d5b37ea0abe9711930d9c3b0b13edec5a0675512',
       'ipa-uk @ git+https://github.com/patriotyk/ipa-uk.git@3faf05ec50fd4880965b6c76f8e479a4f82117f5']
FORMATS = {'.mp3': ['-c:a', 'libmp3lame', '-q:a', '2'], '.ogg': ['-c:a', 'libopus', '-b:a', '64k'],
           '.opus': ['-c:a', 'libopus', '-b:a', '64k'], '.m4a': ['-c:a', 'aac', '-b:a', '128k'],
           '.flac': ['-c:a', 'flac'], '.wav': ['-c:a', 'pcm_s16le']}
GEMINI_CHUNK = 2500          # символів на запит: довший текст ріжемо по реченнях
FEMALE_ENDINGS_EXCEPT = {'микола', 'ілля', 'сава', 'лука', 'хома', 'кузьма', 'фома', 'нікіта', 'саша', 'женя'}


def die(msg: str, code: int = 1):
    print(f'ukr-voice: {msg}', file=sys.stderr)
    sys.exit(code)


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    return few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def say_ok(msg: str):
    print(msg, flush=True)


# ════════════════════════════════════ голоси й пресети ════════════════════════════════════
def gemini_voices() -> list:
    return json.load(open(os.path.join(SKILL, 'assets', 'gemini_voices.json'), encoding='utf-8'))


def load_presets() -> dict:
    """Вбудовані пресети + користувацькі з ~/.config/ukr-voice/presets.json (мають перевагу).
    Пресет: {"note", "gemini": {"voice", "style"}, "holos": {"voice", "speed"?, "expr"?, "pitch"?, "af"?}}.
    Старий формат {"voice": "Speaker_43", ...} розуміється як пресет лише для HolosTTS."""
    res = json.load(open(os.path.join(SKILL, 'assets', 'presets.json'), encoding='utf-8'))
    if os.path.exists(PRESETS):
        try:
            user = json.load(open(PRESETS, encoding='utf-8'))
        except ValueError as e:
            die(f'{PRESETS}: поганий JSON — {e}')
        for k, v in user.items():
            if 'gemini' not in v and 'holos' not in v and 'voice' in v:
                v = {'note': v.get('note', ''), 'holos': {kk: vv for kk, vv in v.items() if kk != 'note'}}
            res[k] = v
    return res


def is_gemini_voice(name: str) -> bool:
    return name.lower() in {v['name'].lower() for v in gemini_voices()}


def canon_gemini_voice(name: str) -> str:
    for v in gemini_voices():
        if v['name'].lower() == name.lower():
            return v['name']
    die(f'немає голосу Gemini «{name}». Список: ukr_voice.py voices')


# ════════════════════════════════════ рушії ════════════════════════════════════
def holos_installed() -> bool:
    return os.path.exists(VPY) and os.path.isdir(os.path.join(HOLOS_DIR, 'holos'))


def holos_commit() -> str:
    try:
        return subprocess.run(['git', '-C', HOLOS_DIR, 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def pick_engine(requested: str, job: dict = None) -> str:
    requested = requested or os.environ.get('UKR_VOICE_ENGINE') or 'auto'
    if requested != 'auto':
        return requested
    voice = (job or {}).get('voice') or ''
    if voice and (voice.startswith('Speaker_') or '*' in voice or '=' in voice):
        return 'holos'
    if voice and is_gemini_voice(voice):
        return 'gemini'
    preset = load_presets().get((job or {}).get('preset') or '', {})
    key, _ = G.find_key()
    if key and (not preset or 'gemini' in preset):
        return 'gemini'
    if holos_installed() and (not preset or 'holos' in preset):
        return 'holos'
    if key:
        return 'gemini'
    die('немає жодного рушія. Хмара (краща якість): ukr_voice.py setup gemini; '
        'офлайн: ukr_voice.py setup holos. Стан: ukr_voice.py doctor')


def resolve(job: dict, engine: str) -> dict:
    """Завдання + пресет → параметри для конкретного рушія. Поля завдання перекривають пресет."""
    presets = load_presets()
    p = {}
    name = job.get('preset')
    if not name and not job.get('voice'):
        name = 'оповідач'
    if name:
        if name not in presets:
            die(f'немає пресету «{name}». Є: {", ".join(presets)}')
        if engine not in presets[name]:
            die(f'пресет «{name}» не має налаштувань для рушія {engine}')
        p = dict(presets[name][engine])
    r = dict(p)
    for k in ('voice', 'style', 'speed', 'expr', 'pitch', 'af', 'light'):
        if job.get(k) not in (None, ''):
            r[k] = job[k]
    if engine == 'gemini':
        r['voice'] = canon_gemini_voice(r.get('voice') or 'Laomedeia')
    elif not r.get('voice'):
        die('для HolosTTS вкажіть --voice або --preset')
    return r


# ── Gemini ──
def gemini_key() -> str:
    key, _ = G.find_key()
    if not key:
        die('немає ключа Gemini. Запустіть у своєму терміналі: python3 ukr_voice.py setup gemini '
            '(або задайте змінну GEMINI_API_KEY). Ключ: https://aistudio.google.com/apikey')
    return key


def gemini_say(text: str, params: dict, model: str, cache: bool) -> list:
    """Повертає список WAV-байтів (по одному на запит; довгий текст ріжемо)."""
    text = M.apply_lexicon(text, LEXICON)
    parts = [{'text': t, 'style': s} for t, s in M.to_gemini(text)]
    chunks, cur, size = [], [], 0
    for p in parts:
        for piece in M.split_sentences(p['text'], GEMINI_CHUNK):
            if cur and size + len(piece) > GEMINI_CHUNK:
                chunks.append(cur)
                cur, size = [], 0
            cur.append({'text': piece, 'style': p['style']})
            size += len(piece)
    if cur:
        chunks.append(cur)
    key = gemini_key()
    return [G.synth(G.build_body(c, params['voice'], model, params.get('style', '')), model, key,
                    os.path.join(CACHE, 'gemini') if cache else None) for c in chunks]


# ── HolosTTS ──
def holos_run(jobs: list) -> None:
    """jobs: [{'text', 'voice', 'out'(.wav), 'light', 'speed', 'expr', 'pitch'}] — одним запуском моделі."""
    if not holos_installed():
        die('HolosTTS не встановлено. Запустіть: ukr_voice.py setup holos')
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(jobs, f, ensure_ascii=False)
        jf = f.name
    env = dict(os.environ, UKR_VOICE_HOME=DATA, UKR_VOICE_HF_REVISION=HF_REVISION, UKR_VOICE_LEXICON=LEXICON,
               TOKENIZERS_PARALLELISM='false', PYTHONWARNINGS='ignore')
    try:
        r = subprocess.run([VPY, os.path.join(HERE, 'holos_engine.py'), 'batch', jf], env=env,
                           capture_output=True, text=True)
        if r.returncode:
            tail = '\n'.join(r.stderr.strip().splitlines()[-6:])
            die(f'HolosTTS завершився з помилкою:\n{tail}\nПеревірте: ukr_voice.py doctor')
    finally:
        os.unlink(jf)


def holos_job(text: str, params: dict, raw: str) -> dict:
    return {'text': text, 'voice': params['voice'], 'out': raw, 'light': params.get('light', True),
            'speed': float(params.get('speed', 1.0)), 'expr': float(params.get('expr', 1.0)),
            'pitch': float(params.get('pitch', 1.0)), 'force': True}


# ════════════════════════════════════ аудіо ════════════════════════════════════
def concat_wavs(blobs_or_paths: list, out: str, gap: float = 0.0) -> None:
    """Склеює WAV (однаковий формат) з паузою gap секунд між шматками. Лише стандартна бібліотека."""
    params, frames = None, []
    for item in blobs_or_paths:
        src = item if isinstance(item, str) else _BytesFile(item)
        with wave.open(src, 'rb') as w:
            if params is None:
                params = w.getparams()
            elif (w.getframerate(), w.getsampwidth(), w.getnchannels()) != \
                    (params.framerate, params.sampwidth, params.nchannels):
                die('шматки аудіо мають різний формат — склеїти без ffmpeg не вийде')
            frames.append(w.readframes(w.getnframes()))
    silence = b'\x00' * int(gap * params.framerate) * params.sampwidth * params.nchannels
    with wave.open(out, 'wb') as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        w.writeframes(silence.join(frames))


class _BytesFile:
    def __init__(self, data: bytes):
        import io
        self.f = io.BytesIO(data)

    def __getattr__(self, n):
        return getattr(self.f, n)


def finish(raw_wav: str, out: str, af: str = '', raw: bool = False) -> None:
    """Обрізає тишу по краях, вирівнює гучність (−16 LUFS, як у подкастах) і зберігає у формат за розширенням."""
    ext = os.path.splitext(out)[1].lower()
    if ext not in FORMATS:
        die(f'невідомий формат «{ext}». Можна: {" ".join(FORMATS)}')
    os.makedirs(os.path.dirname(os.path.abspath(out)) or '.', exist_ok=True)
    if not shutil.which('ffmpeg'):
        if ext != '.wav':
            die('для mp3/ogg/m4a потрібен ffmpeg (macOS: brew install ffmpeg; Linux: apt install ffmpeg) '
                'або збережіть у .wav')
        shutil.copy(raw_wav, out)
        return
    trim = ('silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05,areverse,'
            'silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.1,areverse')
    chain = [] if raw else [trim]
    if af:
        chain.append(af)
    if not raw:
        chain.append('loudnorm=I=-16:TP=-1.5:LRA=11')
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', raw_wav]
    if chain:
        cmd += ['-af', ','.join(chain)]
    cmd += ['-ar', '44100' if ext in ('.mp3', '.m4a') else '48000' if ext in ('.ogg', '.opus') else '24000',
            '-ac', '1'] + FORMATS[ext] + [out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        die(f'ffmpeg: {r.stderr.strip()[-400:]}')


def duration(path: str) -> float:
    try:
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                           capture_output=True, text=True)
        return float(r.stdout.strip())
    except (OSError, ValueError):
        return 0.0


# ════════════════════════════════════ команди ════════════════════════════════════
def cmd_say(a):
    job = {'text': a.text, 'out': a.o, 'preset': a.preset, 'voice': a.voice, 'style': a.style,
           'speed': a.speed, 'expr': a.expr, 'pitch': a.pitch, 'af': a.af}
    if a.full_stress:
        job['light'] = False
    run_jobs([job], a.engine, a.model, not a.no_cache, a.raw)
    if a.subs:
        write_subs(a.o, [('', a.text)])


def run_jobs(jobs: list, engine_req: str, model: str = None, cache: bool = True, raw: bool = False,
             quiet: bool = False) -> None:
    model = G.resolve_model(model)
    tmp = tempfile.mkdtemp(prefix='ukr-voice-')
    try:
        plan = []
        for k, j in enumerate(jobs):
            eng = pick_engine(j.get('engine') or engine_req, j)
            plan.append((k, j, eng, resolve(j, eng)))
        # HolosTTS: усе одним запуском моделі
        hjobs = [holos_job(j['text'], p, os.path.join(tmp, f'{k:04d}.wav')) for k, j, e, p in plan if e == 'holos']
        if hjobs:
            say_ok(f'HolosTTS: озвучую {len(hjobs)} {plural(len(hjobs), "файл", "файли", "файлів")} (запуск моделі ~20–40 с)…')
            holos_run(hjobs)
        # Gemini: паралельно, але помірно, щоб не впертися в ліміти
        gplan = [(k, j, p) for k, j, e, p in plan if e == 'gemini']

        def one(item):
            k, j, p = item
            blobs = gemini_say(j['text'], p, model, cache)
            path = os.path.join(tmp, f'{k:04d}.wav')
            concat_wavs(blobs, path)
            return k

        if gplan:
            with cf.ThreadPoolExecutor(max_workers=min(4, len(gplan))) as ex:
                for fut in cf.as_completed([ex.submit(one, it) for it in gplan]):
                    try:
                        fut.result()
                    except G.GeminiError as e:
                        die(str(e))
        for k, j, e, p in plan:
            finish(os.path.join(tmp, f'{k:04d}.wav'), j['out'], p.get('af', '') if e == 'holos' else '', raw)
            if not quiet:
                d = duration(j['out'])
                say_ok(f'✓ {j["out"]}  ·  {e}: {p["voice"]}' + (f'  ·  {d:.1f} с' if d else ''))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_batch(a):
    try:
        jobs = json.load(open(a.jobs, encoding='utf-8'))
    except (OSError, ValueError) as e:
        die(f'{a.jobs}: {e}')
    for j in jobs:
        if not j.get('text') or not j.get('out'):
            die('кожне завдання має мати "text" і "out"')
    run_jobs(jobs, a.engine, a.model, not a.no_cache, a.raw)


# ── діалог ──
def parse_dialog(path: str) -> list:
    """Сценарій: .txt з рядками «Імʼя: репліка» або .json [{"speaker", "text"}] / [["Імʼя", "репліка"]]."""
    raw = open(path, encoding='utf-8').read()
    if path.endswith('.json'):
        data = json.loads(raw)
        return [(d['speaker'], d['text']) if isinstance(d, dict) else (d[0], d[1]) for d in data]
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = re.match(r'^([^:()\[\]{}/*]{1,40}):\s+(.+)$', line)
        if m:
            lines.append((m.group(1).strip(), m.group(2).strip()))
        elif lines:
            lines[-1] = (lines[-1][0], lines[-1][1] + ' ' + line)
        else:
            die(f'перший рядок сценарію має бути «Імʼя: репліка», а не: {line[:60]}')
    return lines


def guess_female(name: str) -> bool:
    n = name.lower().strip()
    return n.endswith(('а', 'я')) and n not in FEMALE_ENDINGS_EXCEPT


def auto_cast(speakers: list, engine: str) -> dict:
    if engine == 'gemini':
        f = [v['name'] for v in gemini_voices() if v['gender'] == 'f' and v.get('dialog')]
        m = [v['name'] for v in gemini_voices() if v['gender'] == 'm' and v.get('dialog')]
    else:
        f, m = ['Speaker_67'], ['Speaker_42']
    cast, fi, mi = {}, 0, 0
    for s in speakers:
        if guess_female(s):
            if fi >= len(f):
                die(f'забракло жіночих голосів {engine} для автопідбору — задайте --cast')
            cast[s], fi = f[fi], fi + 1
        else:
            if mi >= len(m):
                die(f'забракло чоловічих голосів {engine} для автопідбору — задайте --cast')
            cast[s], mi = m[mi], mi + 1
    return cast


def cmd_dialog(a):
    lines = parse_dialog(a.script)
    if not lines:
        die('сценарій порожній')
    speakers = list(dict.fromkeys(s for s, _ in lines))
    engine = pick_engine(a.engine)
    cast = auto_cast(speakers, engine)
    explicit = {}
    if a.cast:
        for pair in a.cast.split(','):
            if '=' not in pair:
                die(f'--cast: очікую «Імʼя=голос», маю «{pair}»')
            s, v = (x.strip() for x in pair.split('=', 1))
            explicit[s] = v
    presets = load_presets()
    params = {}
    for s in speakers:
        v = explicit.get(s, cast[s])
        if v in presets:
            params[s] = resolve({'preset': v}, engine)
        else:
            params[s] = resolve({'voice': v}, engine)
    say_ok('Ролі: ' + ', '.join(f'{s} → {params[s]["voice"]}' for s in speakers))
    tmp = tempfile.mkdtemp(prefix='ukr-voice-dlg-')
    try:
        pieces = []
        if engine == 'gemini' and not a.split:
            # один запит — природна взаємодія голосів; довгі сцени ріжемо на блоки реплік
            model = G.resolve_model(a.model)
            key = gemini_key()
            blocks, cur, size = [], [], 0
            for s, t in lines:
                if cur and (size + len(t) > GEMINI_CHUNK or len(cur) >= 40):
                    blocks.append(cur)
                    cur, size = [], 0
                cur.append((s, t))
                size += len(t)
            blocks.append(cur)
            for b in blocks:
                parts = []
                for s, t in b:
                    for txt, st in M.to_gemini(M.apply_lexicon(t, LEXICON)):
                        style = [params[s].get('style', '')] + st if params[s].get('style') else st
                        parts.append({'text': txt, 'style': style, 'speaker': s})
                used = {s: params[s]['voice'] for s, _ in b}
                body = G.build_body(parts, used if len(used) > 1 else next(iter(used.values())), model)
                if len(used) == 1:
                    for p in body['contents'][0]['parts']:
                        p.get('speechMetadata', {}).pop('speaker', None)
                try:
                    pieces.append(G.synth(body, model, key, os.path.join(CACHE, 'gemini') if not a.no_cache else None))
                except G.GeminiError as e:
                    die(str(e))
            whole = os.path.join(tmp, 'all.wav')
            concat_wavs(pieces, whole, a.gap)
        else:
            jobs = [{'text': t, 'out': os.path.join(tmp, f'{i:04d}.wav'), 'voice': params[s]['voice'],
                     'style': params[s].get('style', ''), 'engine': engine,
                     **{k: params[s][k] for k in ('speed', 'expr', 'pitch') if k in params[s]}}
                    for i, (s, t) in enumerate(lines)]
            run_jobs(jobs, engine, a.model, not a.no_cache, raw=True, quiet=True)
            if a.split:
                os.makedirs(a.split, exist_ok=True)
                for i, (s, t) in enumerate(lines):
                    safe = re.sub(r'[^\w-]+', '_', s)
                    out = os.path.join(a.split, f'{i + 1:03d}_{safe}.{a.split_format}')
                    finish(jobs[i]['out'], out)
                say_ok(f'✓ окремі репліки: {a.split} ({len(lines)} {plural(len(lines), "файл", "файли", "файлів")})')
            whole = os.path.join(tmp, 'all.wav')
            concat_wavs([j['out'] for j in jobs], whole, a.gap)
        finish(whole, a.o)
        if a.subs:
            write_subs(a.o, lines)
        d = duration(a.o)
        say_ok(f'✓ {a.o}  ·  {len(lines)} {plural(len(lines), "репліка", "репліки", "реплік")}, '
               f'{len(speakers)} {plural(len(speakers), "голос", "голоси", "голосів")}' + (f'  ·  {d:.1f} с' if d else ''))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_audition(a):
    engine = pick_engine(a.engine)
    if a.voices:
        names = [v.strip() for v in a.voices.split(',') if v.strip()]
    elif engine == 'gemini':
        vs = gemini_voices()
        if a.gender:
            vs = [v for v in vs if v['gender'] == a.gender]
        names = [v['name'] for v in vs if a.all or v.get('top')]
    else:
        names = list_holos_voices()
    os.makedirs(a.o, exist_ok=True)
    jobs = [{'text': a.text, 'voice': n, 'engine': engine, 'style': a.style,
             'out': os.path.join(a.o, re.sub(r'[^\w.-]+', '_', n) + '.mp3')} for n in names]
    say_ok(f'Прослуховування: {len(jobs)} голосів ({engine}) → {a.o}')
    run_jobs(jobs, engine, a.model, True)


def list_holos_voices() -> list:
    if not holos_installed():
        die('HolosTTS не встановлено: ukr_voice.py setup holos')
    env = dict(os.environ, UKR_VOICE_HOME=DATA, UKR_VOICE_HF_REVISION=HF_REVISION, PYTHONWARNINGS='ignore')
    r = subprocess.run([VPY, os.path.join(HERE, 'holos_engine.py'), 'voices'], env=env, capture_output=True, text=True)
    if r.returncode:
        last = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'невідома помилка'
        die(f'не вдалося завантажити HolosTTS: {last}. Спробуйте: ukr_voice.py setup holos')
    return [x.strip() for x in r.stdout.splitlines() if x.strip()]


def cmd_voices(a):
    engine = a.engine if a.engine != 'auto' else ('gemini' if G.find_key()[0] or not holos_installed() else 'holos')
    if engine == 'gemini':
        print('Голоси Gemini TTS (★ — рекомендовані для української):\n')
        for g, title in (('f', 'Жіночі'), ('m', 'Чоловічі')):
            print(f'{title}:')
            for v in gemini_voices():
                if v['gender'] == g:
                    print(f'  {"★" if v.get("top") else " "} {v["name"]:15s} {v["character"]}')
            print()
    else:
        for n in list_holos_voices():
            print(n)


def cmd_presets(a):
    for name, p in load_presets().items():
        engines = ' '.join(f'{e}:{p[e]["voice"]}' for e in ('gemini', 'holos') if e in p)
        print(f'{name:16s} {engines:42s} {p.get("note", "")}')
    print(f'\nСвої пресети: {PRESETS}')


# ── перевірка розбірливості ──
def whisper_model() -> str:
    env = os.environ.get('WHISPER_MODEL')
    if env and os.path.exists(env):
        return env
    cands = [p for p in glob.glob(os.path.expanduser('~/.cache/whisper-cpp/ggml-*.bin')) +
             glob.glob('/opt/homebrew/share/whisper-cpp/ggml-*.bin') if not p.endswith('.en.bin')]
    order = ['large-v3-turbo', 'large-v3', 'medium', 'small', 'base', 'tiny']
    cands.sort(key=lambda p: next((i for i, o in enumerate(order) if o in p), 99))
    return cands[0] if cands else ''


def norm_words(t: str) -> str:
    t = M.plain(t).lower().replace('́', '')
    t = re.sub(f"[{re.escape(chr(0x2bc))}’'`]", '', t)
    return ' '.join(re.sub(r'[^\w\s]', ' ', t).split())


def write_subs(audio: str, lines: list, fmt: str = 'both', max_chars: int = 42, quiet: bool = False) -> None:
    """Субтитри поруч з аудіо: lines — [(мовець, розмічений текст)]."""
    exe = shutil.which('whisper-cli') or shutil.which('whisper-cpp')
    formats = ('srt', 'vtt') if fmt == 'both' else (fmt,)
    clean = [(sp, M.plain(t)) for sp, t in lines]
    paths, method = SUBS.make(audio, clean, os.path.splitext(audio)[0], formats, (exe, whisper_model()),
                              duration(audio), max_chars)
    if not quiet:
        note = '' if method == 'whisper' else ' — без Whisper час приблизний (brew install whisper-cpp для точного)'
        say_ok(f'✓ субтитри: {", ".join(paths)} ({method}{note})')


def cmd_subs(a):
    if not os.path.isfile(a.audio):
        die(f'немає файлу {a.audio}')
    if a.script:
        lines = parse_dialog(a.script)
    elif a.text:
        lines = [('', a.text)]
    else:
        die('вкажіть --text "…" або --script сценарій.txt')
    base = os.path.splitext(a.o)[0] if a.o else os.path.splitext(a.audio)[0]
    exe = shutil.which('whisper-cli') or shutil.which('whisper-cpp')
    formats = ('srt', 'vtt') if a.format == 'both' else (a.format,)
    paths, method = SUBS.make(a.audio, [(sp, M.plain(t)) for sp, t in lines], base, formats,
                              (exe, whisper_model()), duration(a.audio), a.max_chars)
    say_ok(f'✓ {", ".join(paths)} ({method})')


def cmd_check(a):
    exe = shutil.which('whisper-cli') or shutil.which('whisper-cpp')
    model = whisper_model()
    if not exe or not model:
        die('для перевірки потрібен whisper.cpp: brew install whisper-cpp і модель, напр. '
            'curl -L -o ~/.cache/whisper-cpp/ggml-small.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin')
    tmp = tempfile.mkdtemp()
    try:
        w16 = os.path.join(tmp, 'a.wav')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', a.audio, '-ar', '16000', '-ac', '1', w16], check=True)
        r = subprocess.run([exe, '-m', model, '-l', 'uk', '-nt', '-f', w16], capture_output=True, text=True)
        heard = ' '.join(r.stdout.split())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'Почуто:   {heard}')
    if a.text:
        exp = M.plain(a.text)
        ratio = difflib.SequenceMatcher(None, norm_words(exp), norm_words(heard)).ratio()
        print(f'Очікував: {exp}')
        print(f'Збіг: {ratio:.0%} — ' + ('добре' if ratio >= .85 else 'варто переслухати' if ratio >= .6 else 'погано'))
        if ratio < a.min:
            sys.exit(1)


# ── встановлення й стан ──
def cmd_setup(a):
    if a.what == 'gemini':
        if not sys.stdin.isatty():
            die('ключ вводиться інтерактивно: запустіть цю команду у власному терміналі '
                '(не через агента), або задайте змінну GEMINI_API_KEY')
        print('Ключ Gemini API: https://aistudio.google.com/apikey (безкоштовний рівень є).')
        key = getpass.getpass('Вставте ключ (не відображається): ').strip()
        if not key:
            die('порожній ключ')
        ok, msg = G.check_key(key, G.resolve_model(None))
        print(('✓ ' if ok else '✖ ') + msg)
        if not ok:
            sys.exit(1)
        os.makedirs(CONF, exist_ok=True)
        with open(CREDS, 'w', encoding='utf-8') as f:
            f.write(f'GEMINI_API_KEY={key}\n')
        os.chmod(CREDS, 0o600)
        print(f'Збережено в {CREDS} (доступ лише для вас).')
        return
    # holos
    if not shutil.which('git'):
        die('потрібен git')
    os.makedirs(DATA, exist_ok=True)
    if not os.path.isdir(HOLOS_DIR):
        subprocess.run(['git', 'clone', '-q', HOLOS_REPO, HOLOS_DIR], check=True)
    if holos_commit() != HOLOS_COMMIT:
        subprocess.run(['git', '-C', HOLOS_DIR, 'fetch', '-q', 'origin'], check=True)
        subprocess.run(['git', '-C', HOLOS_DIR, 'checkout', '-q', HOLOS_COMMIT], check=True)
    if not os.path.exists(VPY) or a.force:
        say_ok('Створюю оточення й ставлю залежності (~2 ГБ, кілька хвилин)…')
        subprocess.run([sys.executable, '-m', 'venv', VENV], check=True)
        subprocess.run([VPY, '-m', 'pip', 'install', '-q', '--upgrade', 'pip'], check=True)
        subprocess.run([VPY, '-m', 'pip', 'install', '-q'] + PIP, check=True)
    say_ok('Перевіряю модель (перший раз качає ваги ~0,5 ГБ)…')
    n = len(list_holos_voices())
    say_ok(f'✓ HolosTTS готовий: {n} голосів. Оточення: {VENV}')


def cmd_doctor(a):
    ok, no = '✔', '✖'
    print(f'ukr-voice {__version__} · Python {platform.python_version()} · {platform.system()} {platform.machine()}\n')
    ff = shutil.which('ffmpeg')
    print(f'{ok if ff else no} ffmpeg' + (f'  {ff}' if ff else '  — потрібен для mp3/ogg/m4a (brew install ffmpeg)'))
    key, where = G.find_key()
    model = G.resolve_model(None)
    if key:
        line = f'{ok} Gemini TTS: ключ знайдено ({where}) · модель {model}'
        if a.online:
            good, msg = G.check_key(key, model)
            line += f' · {msg}' if good else f'\n  {no} {msg}'
        print(line)
    else:
        print(f'{no} Gemini TTS: ключа немає — ukr_voice.py setup gemini (або змінна GEMINI_API_KEY)')
    if holos_installed():
        c = holos_commit()
        stale = c and c != HOLOS_COMMIT
        print(f'{"⚠" if stale else ok} HolosTTS: встановлено ({DATA}) · код {c[:7] or "?"}'
              + (' — застаріла версія, оновіть: ukr_voice.py setup holos' if stale else ''))
    else:
        print(f'{no} HolosTTS: не встановлено — ukr_voice.py setup holos (офлайн, ~2 ГБ)')
    wm = whisper_model()
    wx = shutil.which('whisper-cli')
    print(f'{ok if wx and wm else "–"} Whisper (перевірка розбірливості): '
          + (f'{os.path.basename(wm)}' if wx and wm else 'не знайдено — необовʼязково'))
    try:
        eng = pick_engine('auto')
        print(f'\nРушій за замовчуванням: {eng}')
    except SystemExit:
        print('\nЖоден рушій не готовий.')


def cmd_status(a):
    r = subprocess.run(['pgrep', '-fl', 'holos_engine.py'], capture_output=True, text=True)
    print('Локальний синтез HolosTTS: ' + ('працює\n' + r.stdout if r.stdout.strip() else 'не запущений (памʼять вільна)'))


def cmd_stop(a):
    subprocess.run(['pkill', '-f', 'holos_engine.py'], capture_output=True)
    print('Зупинено. Моделі лишились на диску — наступний запуск без завантажень.')


# ════════════════════════════════════ CLI ════════════════════════════════════
def main(argv=None):
    ap = argparse.ArgumentParser(prog='ukr-voice', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--version', action='version', version=f'ukr-voice {__version__}')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(s, engine=True):
        if engine:
            s.add_argument('--engine', choices=['auto', 'gemini', 'holos'], default='auto')
        s.add_argument('--model', help='модель Gemini: flash (типово), lite або повна назва')
        s.add_argument('--no-cache', action='store_true', help='не брати готове з кешу Gemini')
        s.add_argument('--raw', action='store_true', help='без обрізання тиші й вирівнювання гучності')

    s = sub.add_parser('say', help='озвучити текст')
    s.add_argument('text')
    s.add_argument('-o', required=True, help='вихідний файл (.mp3, .wav, .ogg, .m4a, .flac)')
    s.add_argument('--preset', help='пресет голосу (див. presets)')
    s.add_argument('--voice', help='голос: Gemini (Kore…) або HolosTTS (Speaker_67, суміші)')
    s.add_argument('--style', help='опис подачі для Gemini, напр. "warm, slow, smiling"')
    s.add_argument('--speed', type=float, help='HolosTTS: темп (1.0 — природний)')
    s.add_argument('--expr', type=float, help='HolosTTS: жвавість інтонації (1.0–1.35)')
    s.add_argument('--pitch', type=float, help='HolosTTS: висота (0.85–1.15)')
    s.add_argument('--af', help='HolosTTS: додаткові фільтри ffmpeg')
    s.add_argument('--full-stress', action='store_true', help='HolosTTS: наголос і на односкладових словах')
    s.add_argument('--subs', action='store_true', help='також субтитри .srt і .vtt поруч з аудіо')
    common(s)
    s = sub.add_parser('dialog', help='озвучити діалог кількома голосами')
    s.add_argument('script', help='.txt («Імʼя: репліка») або .json')
    s.add_argument('-o', required=True)
    s.add_argument('--cast', help='ролі: "Оля=Zephyr,Тарас=оповідач-ч" (голос або пресет)')
    s.add_argument('--gap', type=float, default=0.0, help='пауза між блоками/репліками, с')
    s.add_argument('--split', metavar='DIR', help='також зберегти кожну репліку окремим файлом')
    s.add_argument('--split-format', default='mp3')
    s.add_argument('--subs', action='store_true', help='також субтитри .srt і .vtt з іменами мовців')
    common(s)
    s = sub.add_parser('batch', help='багато файлів з JSON')
    s.add_argument('jobs')
    common(s)
    s = sub.add_parser('audition', help='одна фраза різними голосами')
    s.add_argument('text')
    s.add_argument('-o', required=True, help='тека для файлів')
    s.add_argument('--voices', help='через кому')
    s.add_argument('--gender', choices=['f', 'm'])
    s.add_argument('--all', action='store_true', help='усі голоси, не лише рекомендовані')
    s.add_argument('--style')
    common(s)
    s = sub.add_parser('voices', help='список голосів')
    s.add_argument('--engine', choices=['auto', 'gemini', 'holos'], default='auto')
    sub.add_parser('presets', help='пресети голосів')
    s = sub.add_parser('check', help='перевірити розбірливість через Whisper')
    s.add_argument('audio')
    s.add_argument('--text', help='очікуваний текст')
    s.add_argument('--min', type=float, default=0.0, help='код виходу 1, якщо збіг нижче (0–1)')
    s = sub.add_parser('subs', help='субтитри SRT/VTT до готового аудіо')
    s.add_argument('audio')
    s.add_argument('--text', help='текст, що звучить (можна з розміткою)')
    s.add_argument('--script', help='або сценарій діалогу «Імʼя: репліка»')
    s.add_argument('-o', help='базова назва файлів субтитрів (типово — як в аудіо)')
    s.add_argument('--format', choices=['srt', 'vtt', 'both'], default='both')
    s.add_argument('--max-chars', type=int, default=42, help='символів у рядку титру')
    s = sub.add_parser('setup', help='налаштувати рушій')
    s.add_argument('what', choices=['gemini', 'holos'])
    s.add_argument('--force', action='store_true')
    s = sub.add_parser('doctor', help='стан встановлення')
    s.add_argument('--online', action='store_true', help='перевірити ключ Gemini запитом до API')
    sub.add_parser('status')
    sub.add_parser('stop')
    a = ap.parse_args(argv)
    {'say': cmd_say, 'dialog': cmd_dialog, 'batch': cmd_batch, 'audition': cmd_audition, 'voices': cmd_voices,
     'presets': cmd_presets, 'check': cmd_check, 'subs': cmd_subs, 'setup': cmd_setup, 'doctor': cmd_doctor, 'status': cmd_status,
     'stop': cmd_stop}[a.cmd](a)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
