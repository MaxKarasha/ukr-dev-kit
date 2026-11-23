import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, 'tests', 'fixtures')


def add_script_path(skill: str) -> None:
    p = os.path.join(ROOT, 'skills', skill, 'scripts')
    if p not in sys.path:
        sys.path.insert(0, p)


# Скрипти читають файли однорядково (open(...).read()) — у CPython вони закриваються одразу.
import warnings  # noqa: E402

warnings.simplefilter('ignore', ResourceWarning)
