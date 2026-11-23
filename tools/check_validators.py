#!/usr/bin/env python3
"""Проганяє код валідаторів прямо з skills/ukr-data/references/validators.md на тестових векторах:
Python — завжди, TypeScript — якщо є Node 22+, C# — якщо є dotnet (або з --require-all — вимагає всі).

    python3 tools/check_validators.py [--require-all]
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, 'skills', 'ukr-data', 'references', 'validators.md')
VECTORS = {
    'rnokpp': ({'3652504575'}, {'3652504576', '365250457', 'abcdefghij'}),
    'edrpou': ({'14360570', '00032129', '00135390'}, {'14360571', '1436057'}),
    'iban': ({'UA213223130000026007233566001', 'UA21 3223 1300 0002 6007 2335 6600 1'},
             {'UA213223130000026007233566002', 'DE89370400440532013000'}),
    'unzr': ({'20000101-00019', '2000010100019'}, {'20000101-00011', '2000-01-01'}),
}


def blocks(lang):
    text = open(DOC, encoding='utf-8').read()
    return [m.group(1) for m in re.finditer(r'```' + lang + r'\n(.*?)```', text, re.S)]


def expected():
    return {k: {v: True for v in good} | {v: False for v in bad} for k, (good, bad) in VECTORS.items()}


def check_python():
    ns = {}
    exec(blocks('python')[0], ns)
    fns = {'rnokpp': ns['is_valid_rnokpp'], 'edrpou': ns['is_valid_edrpou'], 'iban': ns['is_valid_ua_iban'],
           'unzr': ns['is_valid_unzr']}
    return {k: {v: fns[k](v) for v in cases} for k, cases in expected().items()}


def check_ts():
    node = shutil.which('node')
    if not node:
        return None
    d = tempfile.mkdtemp()
    open(os.path.join(d, 'v.ts'), 'w').write(blocks('ts')[0])
    cases = json.dumps({k: list(v) for k, v in expected().items()})
    open(os.path.join(d, 'run.ts'), 'w').write(
        "import { isValidRnokpp, isValidEdrpou, isValidUaIban, isValidUnzr, decodeRnokpp, plural, normalizeUaPhone } from './v.ts';\n"
        "const f: Record<string, (s: string) => boolean> = {rnokpp: isValidRnokpp, edrpou: isValidEdrpou, iban: isValidUaIban, unzr: isValidUnzr};\n"
        f"const cases: Record<string, string[]> = {cases};\n"
        "const out: Record<string, Record<string, boolean>> = {};\n"
        "for (const k in cases) { out[k] = {}; for (const v of cases[k]) out[k][v] = f[k](v); }\n"
        "const d = decodeRnokpp('3652504575');\n"
        "if (d.birthDate.toISOString().slice(0,10) !== '2000-01-01' || d.sex !== 'male') throw new Error('decodeRnokpp');\n"
        "if (plural(24, ['файл','файли','файлів']) !== 'файли' || plural(11, ['файл','файли','файлів']) !== 'файлів') throw new Error('plural');\n"
        "if (normalizeUaPhone('067 123 45 67') !== '+380671234567' || normalizeUaPhone('123') !== null) throw new Error('phone');\n"
        "console.log(JSON.stringify(out));\n")
    r = subprocess.run([node, '--experimental-strip-types', '--no-warnings', 'run.ts'], cwd=d, capture_output=True,
                       text=True)
    if r.returncode:
        raise SystemExit('TypeScript: ' + r.stderr[-800:])
    return json.loads(r.stdout)


def check_cs():
    dotnet = shutil.which('dotnet')
    if not dotnet:
        return None
    d = tempfile.mkdtemp()
    subprocess.run([dotnet, 'new', 'console', '-o', d, '--force'], capture_output=True, check=True)
    cases = expected()
    lines = ['var res = new System.Collections.Generic.Dictionary<string, bool>();']
    fn = {'rnokpp': 'IsValidRnokpp', 'edrpou': 'IsValidEdrpou', 'iban': 'IsValidUaIban', 'unzr': 'IsValidUnzr'}
    for k, vs in cases.items():
        for v in vs:
            lines.append(f'res["{k}|{v}"] = UaValidators.{fn[k]}("{v}");')
    lines.append('System.Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(res));')
    open(os.path.join(d, 'Program.cs'), 'w').write('\n'.join(lines) + '\n')
    open(os.path.join(d, 'UaValidators.cs'), 'w').write(blocks('csharp')[0])
    r = subprocess.run([dotnet, 'run', '--project', d], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit('C#: ' + (r.stdout + r.stderr)[-1200:])
    flat = json.loads(r.stdout.strip().splitlines()[-1])
    out = {}
    for key, val in flat.items():
        k, v = key.split('|', 1)
        out.setdefault(k, {})[v] = val
    return out


def main():
    exp = expected()
    failed = False
    for name, fn in (('Python', check_python), ('TypeScript', check_ts), ('C#', check_cs)):
        got = fn()
        if got is None:
            print(f'– {name}: пропущено (немає інструмента)')
            if '--require-all' in sys.argv:
                failed = True
            continue
        bad = [(k, v, got[k][v]) for k in exp for v in exp[k] if got[k][v] != exp[k][v]]
        if bad:
            failed = True
            print(f'✖ {name}: ' + '; '.join(f'{k} {v!r} → {g}' for k, v, g in bad))
        else:
            print(f'✔ {name}: {sum(len(v) for v in exp.values())} векторів')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
