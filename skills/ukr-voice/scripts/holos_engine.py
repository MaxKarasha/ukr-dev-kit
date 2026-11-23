"""Рушій синтезу HolosTTS — запускається ЛИШЕ інтерпретатором оточення (див. ukr_voice.py setup holos).

HolosTTS — модель української мови від patriotyk (MIT): https://github.com/patriotyk/HolosTTS

Модель живе тільки під час виконання: завантажилась → озвучила всі завдання → процес завершився,
памʼять звільнена. Тому для локального бекенда нема чого «вимикати».

    holos_engine.py voices
    holos_engine.py batch jobs.json        # [{"text", "voice", "out", "light"?, "speed"?, "expr"?, "pitch"?}]

Текст може містити режисерську розмітку (див. MARKUP нижче і SKILL.md): емоції, паузи, темп, виділення.
"""
import contextlib, io, json, os, re, sys
from unicodedata import normalize

DATA = os.environ.get('UKR_VOICE_HOME', os.path.expanduser('~/.local/share/ukr-voice'))
sys.path.insert(0, os.path.join(DATA, 'HolosTTS'))

import numpy as np
import soundfile as sf
import torch
from ipa_uk import ipa
from ukrainian_word_stress import Stressifier, StressSymbol
import holos.models as _hm
from holos.models import HolosTTS

# Ваги на Hugging Face оновлюються разом із кодом. Закріплюємо ревізію, з якою сумісний закріплений
# коміт коду (див. HOLOS_COMMIT у ukr_voice.py) — інакше нова версія ваг ламає завантаження моделі.
_REV = os.environ.get('UKR_VOICE_HF_REVISION')
if _REV:
    _orig_dl = _hm.hf_hub_download
    _hm.hf_hub_download = lambda *a, **k: _orig_dl(*a, **{**k, 'revision': k.get('revision') or _REV})

SR = 24000
ACUTE = StressSymbol.CombiningAcuteAccent
VOWELS = 'аеєиіїоуюяАЕЄИІЇОУЮЯ'
IPA_VOWELS = 'aɑɐeɛəiɪɨoɔuʊyʉæ'
_model = _stress = None


def model():
    global _model, _stress
    if _model is None:
        torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))
        _model = HolosTTS('patriotyk/HolosTTS', device='cpu')
        _stress = Stressifier()
    return _model


def light_stress(t):
    """Прибирає наголос з односкладових слів («ти́», «на́», «не́») — мова плавніша, без «рубаності»."""
    def fix(m):
        w = m.group(0)
        return w.replace(ACUTE, '') if sum(ch in VOWELS for ch in w) <= 1 else w
    return re.sub(r"[\w'" + ACUTE + r"]+", fix, t)


LEXICON = os.environ.get('UKR_VOICE_LEXICON', os.path.expanduser('~/.config/ukr-voice/lexicon.json'))


def lexicon(t):
    """Словник вимови користувача: {"Ніко": "Ніко+"} — імена й слова, яких не знає словник наголосів."""
    if not os.path.exists(LEXICON):
        return t
    for w, r in json.load(open(LEXICON)).items():
        t = re.sub(r'(?<![\w+])' + re.escape(w) + r'(?![\w+])', r, t)
    return t


def prep(t, light=True, final=True):
    """Підготовка як у демо HolosTTS: «+» після голосної — ручний наголос, тире → пауза.
    final=False — шматок перед паузою всередині репліки: крапку в кінці не дописуємо, інтонація «висить»."""
    t = lexicon(t.strip()).replace('"', '').replace('+', ACUTE)
    t = normalize('NFKC', t)
    t = re.sub(r'[᠆‐‑‒–—―⁻₋−⸺⸻]', '-', t)
    if final and t and t[-1] not in '.?!:-…':
        t += '.'
    t = re.sub(r' - ', ': ', t)
    t = _stress(t)
    return ipa(light_stress(t) if light else t)


def _mix(spec):
    m = model()
    vec = 0
    for part in spec.split('+'):
        name, w = (part.rsplit('*', 1) + ['1'])[:2] if '*' in part else (part, '1')
        name = name.strip()
        if name not in m.voices:
            raise SystemExit(f'Немає голосу «{name}». Список: ukr_voice.py voices --engine holos')
        vec = vec + m.voices[name] * float(w)
    return vec


def voice_vec(spec):
    """Голос: 'Speaker_43'; суміш 'Speaker_43*0.5+Speaker_37*0.5';
    або окремо тембр і манеру: 'timbre=<суміш>;prosody=<суміш>'.
    Вектор голосу HolosTTS = 128 чисел тембру + 128 чисел просодії (паузи, ритм, інтонація)."""
    if 'timbre=' in spec:
        d = dict(p.split('=', 1) for p in spec.split(';'))
        t, pr = _mix(d['timbre']), _mix(d.get('prosody', d['timbre']))
        return torch.cat([t[:128], pr[128:]])
    return _mix(spec)


# ============================ керування подачею ============================
def _shape(f0, energy, pred_dur, c):
    """Покадрово міняє криву висоти й гучність: розмах інтонації (expr), висоту (pitch), гучність (energy).
    Значення задані на кожен звук; розгортаємо їх на кадри й згладжуємо, щоб не було сходинок."""
    reps = (pred_dur * 2).cpu().numpy()
    n = f0.shape[-1]

    def frames(a):
        x = np.repeat(np.asarray(a, np.float32), reps)[:n]
        x = np.pad(x, (0, n - len(x)), mode='edge')
        return np.convolve(np.pad(x, 4, mode='edge'), np.ones(9, np.float32) / 9, mode='valid')

    expr, pitch, egain = frames(c['expr']), frames(c['pitch']), frames(c['energy'])
    f = f0[0].cpu().numpy().astype(np.float32)
    voiced = f > 60
    if voiced.sum() > 5:
        lf = np.log(np.maximum(f, 1))
        mid = np.median(lf[voiced])
        f = np.where(voiced, np.clip(np.exp(mid + expr * (lf - mid)) * pitch, 70, 650), f)
    e = energy[0].cpu().numpy().astype(np.float32) + egain
    return torch.from_numpy(f).unsqueeze(0).to(f0.dtype), torch.from_numpy(e).unsqueeze(0).to(energy.dtype)


def _encode_ctrl(self, tokens, voice, input_lengths, speed=1.0):
    """Копія HolosTTS.encode з керуванням: темп (self.speed і тривалість кожного звука з self.ctrl['dur']),
    а після передбачення — висота, розмах інтонації й гучність (див. _shape)."""
    c = getattr(self, 'ctrl', None)
    voice_acoustic, voice_prosodic = voice[:, :128], voice[:, 128:]
    t_en = self.prosodic_text_encoder(tokens, input_lengths)
    d_en = t_en.transpose(1, 2)
    d = self.duration_predictor(d_en, voice_prosodic, input_lengths)
    duration = torch.sigmoid(d).sum(axis=-1)[0] / (getattr(self, 'speed', 1.0) * float(speed or 1.0))
    if c is not None and len(c['dur']) == duration.shape[0]:
        duration = duration * torch.tensor(c['dur'], dtype=duration.dtype)
    else:
        c = None
    pred_dur = torch.round(duration).long()
    aln = self.onnx_alignment(pred_dur, d_en.size(1))
    en = d_en.transpose(-1, -2) @ aln
    wav_lengths = pred_dur.sum(dim=0, keepdim=True) * 2
    f0, energy = self.prosodic_predictor(en, voice_prosodic, wav_lengths)
    if c is not None and c.get('shape'):
        f0, energy = _shape(f0, energy, pred_dur, c)
    return self.text_encoder(tokens, input_lengths) @ aln, f0, energy, voice_acoustic, wav_lengths


HolosTTS.encode = _encode_ctrl

# ============================ розмітка ============================
MARKUP = """
(радісно) …        емоція з цього місця до кінця репліки чи до наступної емоції
/  //  ///         пауза 0,12 / 0,3 / 0,5 с;  [0.6] — пауза точно в секундах
*слово*            виділити: трохи повільніше, вище й гучніше (можна кілька слів: *ну дуже*)
О~го               протягнути голосну перед «~» (останню голосну слова, якщо «~» в кінці)
{швидко: …}        шматок з особливою подачею; слова можна поєднувати: {тихо повільно: …}
"""
# емоція → (розмах інтонації, висота, темп, гучність)
EMOTIONS = {
    'спокійно': (1.0, 1.0, 1.0, 0.0),
    'радісно': (1.35, 1.05, 1.06, .3),
    'захоплено': (1.55, 1.09, 1.08, .5),
    'здивовано': (1.6, 1.1, .98, .4),
    'обурено': (1.35, 1.03, 1.1, .6),
    'таємниче': (.75, .94, .92, -.7),
    'сумно': (.7, .94, .92, -.5),
    'задумливо': (.85, .97, .95, -.3),
    'гордо': (1.2, .98, .98, .3),
    'налякано': (1.45, 1.1, 1.12, -.2),
    'хитро': (1.25, 1.0, .98, -.2),
}
ALIASES = {'весело': 'радісно', 'сердито': 'обурено', 'злякано': 'налякано', 'пошепки': 'таємниче'}
SPAN = {'швидко': ('speed', 1.2), 'повільно': ('speed', .82), 'тихо': ('energy', -.8), 'голосно': ('energy', .7),
        'високо': ('pitch', 1.1), 'низько': ('pitch', .9), 'рівно': ('expr', .6), 'жваво': ('expr', 1.5)}
PAUSES = {1: .12, 2: .3, 3: .5}
_TOKEN = re.compile(r'\((?P<emo>[^()\s]+)\)|\[(?P<sec>\d+(?:[.,]\d+)?)\]|(?P<slash>/{1,3})|\{(?P<mods>[^:{}]+):'
                    r'|(?P<close>\})|(?P<star>\*)|(?P<ws>\s+)|(?P<ch>.)', re.S)


def parse(text):
    """Розмічений текст → [('pause', сек) | ('word', текст, {expr, pitch, speed, energy, emph, stretch})]."""
    emo, span, emph = EMOTIONS['спокійно'], {}, False
    out, word, attrs = [], '', {}

    def cur():
        a = dict(expr=emo[0], pitch=emo[1], speed=emo[2], energy=emo[3], emph=emph)
        for k, v in span.items():
            a[k] = a[k] + v if k == 'energy' else a[k] * v
        return a

    def flush():
        nonlocal word, attrs
        if word.strip():
            out.append(('word', word, attrs))
        word, attrs = '', {}

    for m in _TOKEN.finditer(text):
        g = m.lastgroup
        if g == 'emo':
            name = ALIASES.get(m['emo'].lower(), m['emo'].lower())
            if name not in EMOTIONS:
                raise SystemExit(f'Невідома емоція «{m["emo"]}». Є: {", ".join(EMOTIONS)}')
            flush(); emo = EMOTIONS[name]
        elif g in ('sec', 'slash'):
            flush()
            out.append(('pause', float(m['sec'].replace(',', '.')) if g == 'sec' else PAUSES[len(m['slash'])]))
        elif g == 'mods':
            flush(); span = {}
            for mod in m['mods'].split():
                if mod.lower() not in SPAN:
                    raise SystemExit(f'Невідома подача «{mod}». Є: {", ".join(SPAN)}')
                k, v = SPAN[mod.lower()]
                span[k] = span.get(k, 0) + v if k == 'energy' else span.get(k, 1.0) * v
        elif g == 'close':
            flush(); span = {}
        elif g == 'star':
            flush(); emph = not emph
        elif g == 'ws':
            flush()
        elif m['ch'] == '~':
            if word:
                attrs['stretch'] = len(re.sub(r'[^' + VOWELS + ']', '', word))   # котра за ліком голосна
        elif not word and m['ch'] in '.,!?…:;»)' and out and out[-1][0] == 'word':
            out[-1] = ('word', out[-1][1] + m['ch'], out[-1][2])   # «*Котів*!» — знак лишається при слові
        else:
            if not word:
                attrs = cur()
            word += m['ch']
    flush()
    return out


def _neutral(a):
    return a['expr'] == 1 and a['pitch'] == 1 and a['speed'] == 1 and a['energy'] == 0 and not a['emph'] \
        and not a.get('stretch')


def _segments(items, limit=120):
    """Слова між паузами; довгі шматки — групами речень до ~120 символів (інтонація не обривається)."""
    segs, cur = [], []
    for it in items:
        if it[0] == 'pause':
            if cur:
                segs.append((cur, it[1])); cur = []
            elif segs:
                segs[-1] = (segs[-1][0], segs[-1][1] + it[1])
        else:
            if cur and re.search(r'[.?!…]["»)]*$', cur[-1][1]) and \
                    len(' '.join(w[1] for w in cur)) + len(it[1]) > limit:
                segs.append((cur, 0.0)); cur = []
            cur.append(it)
    if cur:
        segs.append((cur, 0.0))
    return segs


def _ipa_words(words, light, final):
    """IPA для шматка; транскрибуємо цілим (кращі наголоси), а слова зіставляємо за пробілами."""
    whole = prep(' '.join(w[1] for w in words), light, final)
    parts = whole.split(' ')
    if len(parts) == len(words):
        return parts
    return [prep(w[1], light, final and k == len(words) - 1) for k, w in enumerate(words)]


def _control(words, parts, base_expr, base_pitch):
    """Значення на кожен токен моделі (разом із крайовими нулями) + рядок IPA."""
    tok = model().tokenizer.dict
    dur, expr, pitch, energy = [1.0], [base_expr], [base_pitch], [0.0]
    text = ' '.join(parts)
    for k, (w, p) in enumerate(zip(words, parts)):
        a = w[2]
        vow = [i for i, ch in enumerate(p) if ch in IPA_VOWELS]
        sv = vow[min(a['stretch'], len(vow)) - 1] if a.get('stretch') and vow else -1
        for i, ch in enumerate(p + (' ' if k < len(words) - 1 else '')):
            if ch not in tok:
                continue
            em = a['emph'] and ch != ' '
            dur.append((1 / a['speed']) * (1.25 if em else 1) * (2.4 if i == sv else 1))
            expr.append(base_expr * a['expr'] * (1.2 if em else 1))
            pitch.append(base_pitch * a['pitch'] * (1.1 if em else 1))
            energy.append(a['energy'] + (.5 if em else 0))
    dur.append(1.0); expr.append(expr[-1]); pitch.append(pitch[-1]); energy.append(energy[-1])
    return text, dict(dur=dur, expr=expr, pitch=pitch, energy=energy)


def _tighten(x, max_gap=.3, keep=.2, edge=.03, thr_db=-42):
    """Довгі паузи моделі всередині шматка (> 0,4 с) стискаємо до 0,28 с; тишу по краях обрізаємо."""
    hop = SR // 100
    n = len(x) // hop
    if n < 3:
        return x
    rms = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    loud = 20 * np.log10(rms / (np.abs(x).max() + 1e-9)) > thr_db
    if not loud.any():
        return x
    a, b = int(np.argmax(loud)), n - int(np.argmax(loud[::-1]))
    half, out, k = int(keep * 50), [], a
    while k < b:
        j = k
        while j < b and loud[j] == loud[k]:
            j += 1
        if not loud[k] and j - k > max_gap * 100:
            out += [x[k * hop:(k + half) * hop], x[(j - half) * hop:j * hop]]
        else:
            out.append(x[k * hop:j * hop])
        k = j
    e = int(edge * SR)
    return np.concatenate([x[max(0, a * hop - e):a * hop]] + out + [x[b * hop:b * hop + e]])


def say(text, voice, light=True, speed=1.0, expr=1.0, pitch=1.0):
    """Розмічений текст → хвиля. Без розмітки й з expr=pitch=1 звучить як звичайний синтез."""
    m = model()
    m.speed = speed
    v = voice_vec(voice)
    segs = _segments(parse(text))
    wavs = []
    with torch.no_grad():
        for n, (words, pause) in enumerate(segs):
            last = n == len(segs) - 1
            parts = _ipa_words(words, light, last or not pause)
            ps, c = _control(words, parts, expr, pitch)
            if not m.tokenizer(ps):
                continue
            c['shape'] = not (expr == 1 and pitch == 1 and all(_neutral(w[2]) for w in words))
            m.ctrl = c
            with contextlib.redirect_stdout(io.StringIO()):   # модель друкує налагоджувальні тензори
                wavs.append(_tighten(m.generate(ps, v).squeeze().cpu().numpy()))
            if pause and not last:
                wavs.append(np.zeros(int(pause * SR), np.float32))
    m.ctrl = None
    x = np.concatenate(wavs) if wavs else np.zeros(SR // 4, np.float32)
    return (x / (np.abs(x).max() or 1) * .9).astype(np.float32)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'voices':
        print('\n'.join(model().voices.keys()))
    elif cmd == 'batch':
        jobs = json.load(open(sys.argv[2]))
        for j in jobs:
            if os.path.exists(j['out']) and not j.get('force'):
                print('є', j['out'], flush=True)
                continue
            os.makedirs(os.path.dirname(os.path.abspath(j['out'])), exist_ok=True)
            sf.write(j['out'], say(j['text'], j['voice'], j.get('light', True), j.get('speed', 1.0),
                                   j.get('expr', 1.0), j.get('pitch', 1.0)), SR)
            print('ok', j['out'], flush=True)
    else:
        raise SystemExit(__doc__)
