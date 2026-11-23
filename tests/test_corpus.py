"""Захист від хибних спрацювань: на корпусі грамотного тексту ukr-lint не має знаходити помилок і попереджень."""
import glob
import os
import unittest

from _paths import ROOT, add_script_path

add_script_path('ukr-proofread')
import ukr_lint  # noqa: E402

CORPUS = os.path.join(ROOT, 'tests', 'corpus')


@unittest.skipUnless(os.path.isdir(CORPUS), 'корпусу немає (sdist його не містить)')
class CorpusTest(unittest.TestCase):
    def test_no_false_positives(self):
        linter = ukr_lint.Linter(ukr_lint.Config())
        files = sorted(glob.glob(os.path.join(CORPUS, '*.txt')))
        self.assertGreaterEqual(len(files), 5)
        problems = []
        for path in files:
            text = open(path, encoding='utf-8').read()
            lines = text.split('\n')
            issues, _ = ukr_lint.lint_file(linter, path, text)
            for i in issues:
                if i.level in ('error', 'warning'):
                    ctx = lines[i.line - 1][max(0, i.col - 40):i.col + 40]
                    problems.append(f'{os.path.basename(path)}:{i.line}:{i.col} [{i.rule}] {i.message}\n    …{ctx}…')
        self.assertEqual(problems, [], '\nХибні спрацювання на грамотному тексті — виправте правило:\n'
                         + '\n'.join(problems[:30]))

    def test_corpus_size(self):
        total = sum(os.path.getsize(p) for p in glob.glob(os.path.join(CORPUS, '*.txt')))
        self.assertGreater(total, 300_000)


if __name__ == '__main__':
    unittest.main()
