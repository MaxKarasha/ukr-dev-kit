"""Пакет PyPI: точки входу знаходять скрипти скілів і повертають їхній код виходу."""
import contextlib
import io
import os
import sys
import unittest

from _paths import ROOT

sys.path.insert(0, os.path.join(ROOT, 'src'))
from ukr_dev_kit import __version__, cli  # noqa: E402


class CliTest(unittest.TestCase):
    def run_cmd(self, fn, *argv):
        old = sys.argv
        sys.argv = ['x', *argv]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
                fn()
        finally:
            sys.argv = old
        return cm.exception.code, out.getvalue()

    def test_skills_dir_in_repo(self):
        self.assertTrue(os.path.isfile(os.path.join(cli.skills_dir(), 'ukr-proofread', 'SKILL.md')))

    def test_lint_exit_codes(self):
        self.assertEqual(self.run_cmd(cli.lint, '--no-color', '-t', 'Нажміть тут')[0], 1)
        self.assertEqual(self.run_cmd(cli.lint, '--no-color', '-t', 'Натисніть тут')[0], 0)

    def test_data(self):
        code, out = self.run_cmd(cli.data, 'amount', '2')
        self.assertEqual((code, out.strip()), (0, 'Дві гривні 00 копійок'))

    def test_versions_match(self):
        code, out = self.run_cmd(cli.data, 'amount', '1')
        import ukr_data
        self.assertEqual(ukr_data.__version__, __version__)


if __name__ == '__main__':
    unittest.main()
