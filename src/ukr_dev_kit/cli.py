"""Точки входу консольних команд. Кожна команда запускає скрипт відповідного скіла.

У встановленому пакеті скіли лежать у ukr_dev_kit/skills; під час розробки (pip install -e .) —
у корені репозиторію.
"""
from __future__ import annotations

import importlib
import os
import sys
from typing import NoReturn

_HERE = os.path.dirname(os.path.abspath(__file__))


def skills_dir() -> str:
    for cand in (os.path.join(_HERE, 'skills'), os.path.join(_HERE, '..', '..', 'skills')):
        if os.path.isdir(cand):
            return os.path.abspath(cand)
    raise SystemExit('ukr-dev-kit: не знайдено теку skills — перевстановіть пакет')


def _run(skill: str, module: str) -> NoReturn:
    scripts = os.path.join(skills_dir(), skill, 'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    mod = importlib.import_module(module)
    try:
        code = mod.main()
    except KeyboardInterrupt:
        code = 130
    except BrokenPipeError:
        code = 0
    sys.exit(code or 0)


def lint() -> NoReturn:
    _run('ukr-proofread', 'ukr_lint')


def i18n() -> NoReturn:
    _run('ukr-i18n', 'i18n_check')


def data() -> NoReturn:
    _run('ukr-data', 'ukr_data')


def voice() -> NoReturn:
    _run('ukr-voice', 'ukr_voice')


def ai_tells() -> NoReturn:
    _run('ukr-humanize', 'ukr_ai_tells')
