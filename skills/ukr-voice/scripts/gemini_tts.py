"""Gemini TTS: синтез мовлення через Gemini API (generateContent з responseModalities=AUDIO).

Лише стандартна бібліотека. Сучасні моделі (gemini-3.x) отримують опис подачі в speechMetadata.style
кожної частини тексту, тож він не озвучується; старші (gemini-2.5) — текстовим префіксом.
Діалог — multiSpeakerVoiceConfig, частини з speechMetadata.speaker.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import time
import urllib.error
import urllib.request
from typing import Optional

API = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
DEFAULT_MODEL = 'gemini-3.8-flash-tts'
MODEL_ALIASES = {'flash': 'gemini-3.8-flash-tts', 'lite': 'gemini-3.8-flash-lite-tts',
                 'flash-3.1': 'gemini-3.1-flash-tts-preview', 'pro-2.5': 'gemini-2.5-pro-preview-tts'}
RATE = 24000
KEY_FILES = ['~/.config/ukr-voice/credentials', '~/.config/gemini/credentials']


class GeminiError(RuntimeError):
    pass


def resolve_model(m: Optional[str]) -> str:
    m = m or os.environ.get('UKR_VOICE_GEMINI_MODEL') or DEFAULT_MODEL
    return MODEL_ALIASES.get(m, m)


def find_key() -> tuple:
    """(ключ, звідки). Порядок: GEMINI_API_KEY, GOOGLE_API_KEY, ~/.config/ukr-voice/credentials,
    ~/.config/gemini/credentials (рядок GEMINI_API_KEY=…). Ключ ніколи не друкується."""
    for k in ('GEMINI_API_KEY', 'GOOGLE_API_KEY'):
        if os.environ.get(k):
            return os.environ[k].strip(), f'${k}'
    for p in KEY_FILES:
        fp = os.path.expanduser(p)
        if os.path.isfile(fp):
            for line in open(fp, encoding='utf-8'):
                if line.strip().startswith(('GEMINI_API_KEY=', 'GOOGLE_API_KEY=')):
                    v = line.split('=', 1)[1].strip().strip('"\'')
                    if v:
                        return v, p
    return None, None


def is_modern(model: str) -> bool:
    return not model.startswith(('gemini-2.', 'gemini-1.'))


def build_body(parts: list, voice, model: str, base_style: str = '') -> dict:
    """parts: [{'text', 'style': [..], 'speaker'?}]; voice: назва голосу або {speaker: голос}."""
    modern = is_modern(model)
    out = []
    for p in parts:
        styles = [s for s in ([base_style] if base_style else []) + list(p.get('style') or []) if s]
        part = {'text': p['text']}
        if modern:
            meta = {}
            if styles:
                meta['style'] = '; '.join(styles)
            if p.get('speaker'):
                meta['speaker'] = p['speaker']
            if meta:
                part['speechMetadata'] = meta
        else:
            prefix = f"{p['speaker']}: " if p.get('speaker') else ''
            if styles and not p.get('speaker'):
                prefix = f"Read in this manner ({'; '.join(styles)}): "
            part = {'text': prefix + p['text']}
        out.append(part)
    if not modern:                               # старі моделі — один текстовий блок
        out = [{'text': '\n'.join(x['text'] for x in out)}]
    if isinstance(voice, dict):
        speech = {'multiSpeakerVoiceConfig': {'speakerVoiceConfigs': [
            {'speaker': s, 'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': v}}} for s, v in voice.items()]}}
    else:
        speech = {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voice}}}
    return {'contents': [{'role': 'user', 'parts': out}],
            'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': speech}}


def pcm_to_wav(pcm: bytes, rate: int = RATE) -> bytes:
    return (b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVEfmt ' +
            struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16) + b'data' + struct.pack('<I', len(pcm)) + pcm)


def synth(body: dict, model: str, key: str, cache_dir: Optional[str] = None, retries: int = 4) -> bytes:
    """Виконує запит і повертає WAV (24 кГц, 16 біт, моно). Повторює при 429/5xx; кешує за вмістом запиту."""
    digest = hashlib.sha256(json.dumps([model, body], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]
    cached = os.path.join(cache_dir, digest + '.wav') if cache_dir else None
    if cached and os.path.exists(cached):
        return open(cached, 'rb').read()
    req = urllib.request.Request(API.format(model=model), data=json.dumps(body).encode(), method='POST',
                                 headers={'Content-Type': 'application/json', 'x-goog-api-key': key})
    delay = 3.0
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors='replace')
            try:
                msg = json.loads(msg)['error']['message']
            except (ValueError, KeyError, TypeError):
                pass
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            hint = {400: 'перевірте текст і назву голосу', 403: 'ключ недійсний або без доступу до моделі',
                    404: f'модель {model} недоступна для цього ключа', 429: 'вичерпано ліміт запитів — спробуйте пізніше'}
            raise GeminiError(f'Gemini HTTP {e.code}: {hint.get(e.code, "")}. {str(msg)[:400]}')
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise GeminiError(f'немає зʼєднання з Gemini API: {e.reason}')
    try:
        inline = next(p['inlineData'] for c in data.get('candidates', []) for p in c['content']['parts']
                      if 'inlineData' in p)
    except (StopIteration, KeyError):
        reason = (data.get('candidates') or [{}])[0].get('finishReason') or data.get('promptFeedback')
        raise GeminiError(f'Gemini не повернув аудіо (причина: {reason})')
    audio = base64.b64decode(inline['data'])
    if not audio.startswith(b'RIFF'):
        rate = RATE
        mime = inline.get('mimeType', '')
        if 'rate=' in mime:
            rate = int(mime.split('rate=')[1].split(';')[0])
        audio = pcm_to_wav(audio, rate)
    if cached:
        os.makedirs(cache_dir, exist_ok=True)
        open(cached, 'wb').write(audio)
    return audio


def check_key(key: str, model: str) -> tuple:
    """Перевіряє ключ і доступ до моделі без синтезу. (ok, повідомлення)"""
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{model}',
                                 headers={'x-goog-api-key': key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            json.load(r)
        return True, f'ключ дійсний, модель {model} доступна'
    except urllib.error.HTTPError as e:
        return False, f'HTTP {e.code}: ' + ('модель недоступна' if e.code == 404 else 'ключ недійсний або без доступу')
    except urllib.error.URLError as e:
        return False, f'немає зʼєднання: {e.reason}'
