import json
import os
import subprocess
import sys
import unittest

from _paths import ROOT, FIXTURES, add_script_path

add_script_path('ukr-i18n')
import i18n_check as I  # noqa: E402

CLI = os.path.join(ROOT, 'skills', 'ukr-i18n', 'scripts', 'i18n_check.py')


def run(*args):
    r = subprocess.run([sys.executable, CLI, '--format', 'json', *args], capture_output=True, text=True,
                       cwd=FIXTURES)
    return json.loads(r.stdout or '[]'), r.returncode


class AutoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items, cls.code = run('--auto', 'i18n', '--lint')

    def codes(self, path_part, key=None):
        return {i['code'] for i in self.items if path_part in i['path'] and (key is None or i['key'] == key)}

    def test_exit_code(self):
        self.assertEqual(self.code, 1)

    def test_json_locale(self):
        self.assertIn('missing', self.codes('uk.json', 'nav.logout'))
        self.assertIn('placeholder', self.codes('uk.json', 'greeting'))
        self.assertIn('plural', self.codes('uk.json', 'files_*'))
        self.assertIn('plural', self.codes('uk.json', 'cart'))
        self.assertIn('untranslated', self.codes('uk.json', 'welcome'))
        self.assertIn('tags', self.codes('uk.json', 'terms'))
        self.assertIn('extra', self.codes('uk.json', 'old_key'))
        self.assertIn('lint:surzhyk/настройка', self.codes('uk.json', 'nav.settings'))
        self.assertEqual(self.codes('uk.json', 'api'), set())          # «API» — не помилка
        self.assertEqual(self.codes('uk.json', 'apples'), set())       # 3 форми vue-i18n — добре

    def test_android_ok(self):
        self.assertEqual(self.codes('strings.xml'), set())

    def test_po(self):
        self.assertIn('locale-code', self.codes('messages.po'))
        self.assertIn('plural', self.codes('messages.po', '(header)'))
        self.assertIn('empty', self.codes('messages.po', 'Delete'))
        self.assertIn('lint:surzhyk/сохраняти', self.codes('messages.po', 'Save'))


class UnitTest(unittest.TestCase):
    def test_placeholders(self):
        self.assertEqual(I.placeholders('Hi {{name}}, {count} %s %1$d :attr'),
                         {'{{name}}', '{count}', '%s', '%1$d', ':attr'})
        self.assertEqual(I.placeholders('{n, plural, one {# file} other {# files}}'), {'{n}'})

    def test_icu_forms(self):
        self.assertEqual(I.icu_forms('{n, plural, one {a} few {b} many {c} other {d}}'), {'one', 'few', 'many', 'other'})
        self.assertIsNone(I.icu_forms('просто текст'))

    def test_base_lookup(self):
        here = os.getcwd()
        os.chdir(FIXTURES)
        try:
            self.assertEqual(I.base_for(os.path.join('i18n', 'locales', 'uk.json'), ['en']),
                             os.path.join('i18n', 'locales', 'en.json'))
            self.assertEqual(I.base_for(os.path.join('i18n', 'android', 'values-uk', 'strings.xml'), ['en']),
                             os.path.join('i18n', 'android', 'values', 'strings.xml'))
        finally:
            os.chdir(here)


if __name__ == '__main__':
    unittest.main()
