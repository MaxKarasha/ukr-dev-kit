import json
import os
import subprocess
import sys
import tempfile
import unittest

from _paths import ROOT, FIXTURES, add_script_path

add_script_path('ukr-proofread')
import ukr_lint  # noqa: E402

LINT = os.path.join(ROOT, 'skills', 'ukr-proofread', 'scripts', 'ukr_lint.py')


def rules_of(text, level='hint', **cfg):
    linter = ukr_lint.Linter(ukr_lint.Config(**cfg))
    return [i.rule for i in linter.check_text(text) if ukr_lint.LEVELS[i.level] >= ukr_lint.LEVELS[level]]


class SurzhykTest(unittest.TestCase):
    def test_catches_common_errors(self):
        cases = {
            'Сервіс являється лідером': 'surzhyk/являтися',
            'Прийміть участь у конкурсі': 'calque/приймати-участь',
            'на протязі тижня': 'calque/на-протязі',
            'В залежності від умов': 'calque/в-залежності',
            'Слідуючий крок': 'surzhyk/слідуючий',
            'Відкрийте настройки': 'surzhyk/настройка',
            'Нажміть кнопку': 'surzhyk/нажимати',
            'Самий кращий вибір': 'surzhyk/самий-кращий',
            'Дані співпадають': 'surzhyk/співпадати',
            'по замовчуванню': 'surzhyk/по-замовчуванню',
            'згідно наказу': 'calque/згідно-без-з',
            'біля 10 хвилин': 'surzhyk/біля-числа',
            'так як немає часу': 'calque/так-як',
        }
        for text, rule in cases.items():
            with self.subTest(text=text):
                self.assertIn(rule, rules_of(text))

    def test_no_false_positives_on_good_text(self):
        text = open(os.path.join(FIXTURES, 'good.txt'), encoding='utf-8').read()
        found = ukr_lint.Linter().check_text(text)
        self.assertEqual([(i.rule, i.message) for i in found], [])

    def test_valid_words_that_look_like_surzhyk(self):
        for text in ['Новина зʼявляється', 'Він удалий', 'Заказник у лісі', 'Гроші на рахунок у банку',
                     'Робіть так, як треба', 'Згідно з наказом', 'Скачуть коні']:
            with self.subTest(text=text):
                self.assertEqual(rules_of(text, 'warning'), [])


class TypographyTest(unittest.TestCase):
    def fix(self, text, **cfg):
        linter = ukr_lint.Linter(ukr_lint.Config(**cfg))
        _, edits = ukr_lint.lint_file(linter, 'x.txt', text)
        return ukr_lint.apply_edits(text, edits)

    def test_quotes_dash_ellipsis(self):
        self.assertEqual(self.fix('Натисніть "Зберегти" - і готово...'), 'Натисніть «Зберегти» — і готово…')

    def test_apostrophe_configurable(self):
        self.assertEqual(self.fix("пам'ять і м’ята"), 'памʼять і мʼята')
        self.assertEqual(self.fix("пам'ять", apostrophe='’'), 'пам’ять')

    def test_mixed_alphabet(self):
        self.assertEqual(self.fix('Пpивiт'), 'Привіт')            # латинські p та i
        self.assertIn('alphabet/mixed', rules_of('Пpивiт'))

    def test_spaces(self):
        self.assertEqual(self.fix('Так , звісно,дякую'), 'Так, звісно, дякую')

    def test_template_rules_autofix(self):
        self.assertEqual(self.fix('Відео-урок на веб-сайті пів години'), 'Відеоурок на вебсайті півгодини')

    def test_russian_letters(self):
        self.assertIn('alphabet/russian-letter', rules_of('Це бэкап і щось'))

    def test_russian_text_is_skipped(self):
        self.assertEqual(rules_of('Это просто русский текст', 'warning'), [])


class FormatsTest(unittest.TestCase):
    def lint(self, name, content, *args):
        d = tempfile.mkdtemp()
        p = os.path.join(d, name)
        open(p, 'w', encoding='utf-8').write(content)
        r = subprocess.run([sys.executable, LINT, '--format', 'json', *args, p], capture_output=True, text=True, cwd=d)
        return json.loads(r.stdout or '[]'), p, r.returncode

    def test_json_keys_ignored_values_checked_and_fixed(self):
        issues, p, code = self.lint('uk.json', '{"настройки": "Відкрийте \\"Профіль\\" - тут", "en": "Settings"}', '--fix')
        self.assertEqual(json.load(open(p, encoding='utf-8')), {'настройки': 'Відкрийте «Профіль» — тут', 'en': 'Settings'})

    def test_markdown_code_skipped(self):
        issues, _, code = self.lint('a.md', 'Текст.\n\n```\nявляється - "так"\n```\n\n`являється`\n')
        self.assertEqual(issues, [])
        self.assertEqual(code, 0)

    def test_disable_block(self):
        issues, _, _ = self.lint('a.md', '<!-- ukr-lint-disable -->\nна протязі\n<!-- ukr-lint-enable -->\nна протязі\n')
        self.assertEqual([i['line'] for i in issues], [4])

    def test_code_strings_and_exit_code(self):
        issues, _, code = self.lint('a.ts', 'const a = "Нажміть тут"; // коментар являється\nconst b = "OK";\n')
        self.assertEqual(sorted(i['rule'] for i in issues), ['surzhyk/нажимати', 'surzhyk/являтися'])
        self.assertEqual(code, 1)

    def test_github_format(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'a.txt')
        open(p, 'w', encoding='utf-8').write('Нажміть тут')
        r = subprocess.run([sys.executable, LINT, '--format', 'github', p], capture_output=True, text=True)
        self.assertTrue(r.stdout.startswith('::error file='))


class RulesFilesTest(unittest.TestCase):
    def test_rules_load_and_are_unique(self):
        rules = ukr_lint.load_rules()
        self.assertGreater(len(rules), 100)
        self.assertEqual(len(rules), len({r.id for r in rules}))

    def test_every_rule_has_explanation(self):
        for r in ukr_lint.load_rules():
            self.assertTrue(r.suggestion and r.explanation, r.id)


class DiffModeTest(unittest.TestCase):
    def test_only_changed_lines(self):
        d = tempfile.mkdtemp()
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.com', GIT_COMMITTER_NAME='t',
                   GIT_COMMITTER_EMAIL='t@example.com')

        def git(*a):
            subprocess.run(['git', *a], cwd=d, check=True, capture_output=True, env=env)
        git('init', '-q')
        open(os.path.join(d, 'a.md'), 'w', encoding='utf-8').write('Стара помилка: являється.\n')
        git('add', '.')
        git('commit', '-qm', 'init')
        open(os.path.join(d, 'a.md'), 'a', encoding='utf-8').write('Нова помилка: на протязі.\n')
        r = subprocess.run([sys.executable, LINT, '--diff', '--format', 'json'], cwd=d, capture_output=True, text=True)
        issues = json.loads(r.stdout)
        self.assertEqual([(i['line'], i['rule']) for i in issues], [(2, 'calque/на-протязі')])


if __name__ == '__main__':
    unittest.main()
