import glob
import json
import os
import subprocess
import sys
import unittest

from _paths import ROOT, add_script_path

add_script_path('ukr-humanize')
import ukr_ai_tells  # noqa: E402

SCRIPT = os.path.join(ROOT, 'skills', 'ukr-humanize', 'scripts', 'ukr_ai_tells.py')
RULES = ukr_ai_tells.load_rules()


def keys(text):
    fs, _ = ukr_ai_tells.scan(text, rules=RULES)
    return [f.key for f in fs]


class LexiconTest(unittest.TestCase):
    def test_catches_common_tells(self):
        cases = {
            'Варто зазначити, що кеш працює.': 'варто-зазначити',
            'Давайте розберемося, як це працює.': 'давайте',
            'Це був не просто борг — це був виклик.': 'не-просто-а',
            'Монорепозиторій відіграє ключову роль у розробці.': 'грає-роль',
            'Це стало справжнім свідченням зрілості.': 'свідчення',
            'Ми додали кеш, забезпечуючи стабільність.': 'дієприслівник-хвіст',
            'Готель може похвалитися басейном.': 'може-похвалитися',
            'У сучасному світі все змінюється.': 'у-сучасному-світі',
            'Сподіваюся, ця стаття була корисною!': 'сподіваюся',
            'Хочете, я підготую ще варіант?': 'хочете-я',
            'Це лише початок.': 'це-лише-початок',
        }
        for text, key in cases.items():
            with self.subTest(text=text):
                self.assertIn(key, keys(text))

    def test_rule_starting_with_punctuation_matches(self):
        # шаблон починається з коми — межа слова не повинна його блокувати
        self.assertIn('дієприслівник-хвіст', keys('Час зменшився, підкреслюючи переваги підходу.'))

    def test_same_section_counted_once(self):
        ks = keys('Це не просто оптимізація — це фундамент.')
        self.assertEqual(sum(k in ('не-просто-а', 'не-x-це-y') for k in ks), 1)

    def test_technical_unique_is_fine(self):
        self.assertNotIn('вражаючий', keys('Бери кількість унікальних користувачів за тиждень.'))
        self.assertIn('вражаючий', keys('Це унікальний досвід. Давайте розберемося.'))

    def test_disable_directives(self):
        text = ('<!-- ukr-ai-tells-disable -->\nВарто зазначити, що це не просто X — це Y.\n<!-- ukr-ai-tells-enable -->\n'
                'Звичайне речення. <!-- ukr-ai-tells-disable-line --> Давайте розберемося.\n'
                '<!-- ukr-ai-tells-disable-next-line -->\nУ сучасному світі все інакше.\n')
        self.assertEqual(keys(text), [])
        self.assertIn('давайте', keys('Давайте розберемося.'))

    def test_skips_code(self):
        text = '```\n// Варто зазначити: це не просто код — це тест\n```\nЗвичайне речення.'
        self.assertEqual(keys(text), [])


class StructureTest(unittest.TestCase):
    def test_title_case_heading(self):
        self.assertIn('title-case', keys('# Як Ми Перейшли На Монорепозиторій\n\nТекст.'))
        self.assertNotIn('title-case', keys('# Як ми перейшли на монорепозиторій у Києві\n\nТекст.'))

    def test_grammatical_dash_is_not_connector(self):
        text = 'Київ — столиця України. Python — мова програмування. Харків — місто на сході.'
        self.assertNotIn('connector-dash', keys(text))

    def test_connector_dashes(self):
        text = ('Ми перейшли на монорепозиторій — і що з цього вийшло. Запит ішов у базу — тепер у кеш. '
                'Ми мали 23 репозиторії — але тепер один.')
        self.assertIn('connector-dash', keys(text))

    def test_bold_labels(self):
        text = '- **Швидкість:** швидше.\n- **Узгодженість:** одна версія.\n- **Прозорість:** видно все.\n'
        self.assertIn('bold-labels', keys(text))

    def test_informal_text_is_clean(self):
        text = 'ну таке. замовив у пт, привезли в середу, коробка мокра. дзвонив двічі — ніхто не бере. жах.'
        fs, words = ukr_ai_tells.scan(text, rules=RULES)
        self.assertEqual(ukr_ai_tells.summarize(fs, words)['verdict'], 'слідів ШІ-стилю майже немає')


class Calibration2026Test(unittest.TestCase):
    def test_placeholders_and_markup_by_channel(self):
        text = "Шановний [Ім'я]! Знижка **10 %** діє до [дата]. Див. [наш сайт](https://x.ua)."
        fs, _ = ukr_ai_tells.scan(text, rules=RULES, channel='email')
        ks = [f.key for f in fs]
        self.assertIn('placeholder', ks)
        self.assertIn('markup-in-plain', ks)
        fs, _ = ukr_ai_tells.scan(text, rules=RULES, channel='markdown')
        self.assertNotIn('markup-in-plain', [f.key for f in fs])
        # посилання [текст](url) — не заглушка
        self.assertNotIn('placeholder', keys('Див. [документацію](https://x.ua) і [README](README.md).'))

    def test_label_dash(self):
        text = '- **Діагностика** — визначаємо несправність\n- **Ремонт** — міняємо деталь\n- **Гарантія** — 12 місяців\n'
        self.assertIn('label-dash', keys(text))

    def test_conclusion_heading_is_strong(self):
        fs, _ = ukr_ai_tells.scan('## Висновок\n\nОтже, все добре.', rules=RULES)
        self.assertEqual(next(f.strength for f in fs if f.key == 'conclusion-heading'), 'strong')

    def test_title_case_is_weak_now(self):
        fs, _ = ukr_ai_tells.scan('# Як Ми Перейшли На Монорепозиторій\n\nТекст.', rules=RULES)
        self.assertEqual(next(f.strength for f in fs if f.key == 'title-case'), 'weak')

    def test_isolated_weak_word_is_dropped(self):
        self.assertEqual(keys('Це ключове слово в запиті.'), [])

    def test_human_signals_reported(self):
        ukr_ai_tells.scan('Привіт, Олено - надсилаю звіт. Дякую за iнформацію.', rules=RULES)
        hs = ukr_ai_tells.scan.human_signals
        self.assertTrue(any('дефіс' in h for h in hs))
        self.assertTrue(any('латинські' in h for h in hs))

    def test_why_choose_us(self):
        self.assertIn('чому-обирають-нас', keys('## Чому обирають нас\n\nМи найкращі. Чекаємо на вас!'))


class CorpusTest(unittest.TestCase):
    """Людські тексти (Конституція, Вікіпедія) не мають отримувати вердикт «є ознаки ШІ»."""

    def test_human_corpus_is_clean(self):
        files = glob.glob(os.path.join(ROOT, 'tests', 'corpus', '*.txt'))
        if not files:
            self.skipTest('корпусу немає (sdist)')
        for f in files:
            with self.subTest(file=os.path.basename(f)):
                with open(f, encoding='utf-8') as fh:
                    fs, words = ukr_ai_tells.scan(fh.read(), f, RULES)
                s = ukr_ai_tells.summarize(fs, words)
                self.assertLess(s['density_per_1000'], 6, s)


class CliTest(unittest.TestCase):
    def test_json_and_exit_code(self):
        text = 'Варто зазначити, що це не просто кеш — це фундамент. Давайте розберемося. Майбутнє виглядає яскравим!'
        r = subprocess.run([sys.executable, SCRIPT, '-t', text, '--format', 'json', '--max-score', '5'],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        data = json.loads(r.stdout)
        self.assertGreaterEqual(data[0]['summary']['findings'], 4)
        self.assertNotIn('span', data[0]['findings'][0])


if __name__ == '__main__':
    unittest.main()
