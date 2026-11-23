import datetime as dt
import random
import unittest

from _paths import add_script_path

add_script_path('ukr-data')
import ukr_data as D  # noqa: E402


class ChecksumsTest(unittest.TestCase):
    def test_rnokpp(self):
        r = D.check_rnokpp('3652504575')
        self.assertTrue(r['valid'])
        self.assertEqual(r['birth_date'], '2000-01-01')
        self.assertEqual(r['sex'], 'чоловіча')
        self.assertFalse(D.check_rnokpp('3652504576')['valid'])
        self.assertFalse(D.check_rnokpp('123')['valid'])

    def test_edrpou_real_codes(self):
        for code in ('14360570', '00032129', '00135390'):     # ПриватБанк, Ощадбанк, Укрнафта
            self.assertTrue(D.check_edrpou(code)['valid'], code)
        self.assertFalse(D.check_edrpou('14360571')['valid'])

    def test_iban(self):
        r = D.check_iban('UA21 3223 1300 0002 6007 2335 6600 1')
        self.assertTrue(r['valid'])
        self.assertEqual(r['mfo'], '322313')
        self.assertFalse(D.check_iban('UA213223130000026007233566002')['valid'])
        self.assertFalse(D.check_iban('DE89370400440532013000')['valid'])

    def test_unzr(self):
        self.assertTrue(D.check_unzr('20000101-00019')['valid'])
        self.assertTrue(D.check_unzr('2000010100019')['valid'])
        self.assertFalse(D.check_unzr('20000101-00011')['valid'])
        self.assertFalse(D.check_unzr('20001301-00019')['valid'])     # 13-й місяць

    def test_phone(self):
        for raw in ('067 123 45 67', '+38 (067) 123-45-67', '380671234567', '80671234567'):
            r = D.check_phone(raw)
            self.assertTrue(r['valid'], raw)
            self.assertEqual(r['e164'], '+380671234567')
            self.assertEqual(r['operator'], 'Київстар')
        self.assertFalse(D.check_phone('12345')['valid'])

    def test_detect(self):
        self.assertEqual(D.detect('3652504575'), 'rnokpp')
        self.assertEqual(D.detect('14360570'), 'edrpou')
        self.assertEqual(D.detect('UA213223130000026007233566001'), 'iban')
        self.assertEqual(D.detect('20000101-00019'), 'unzr')
        self.assertEqual(D.detect('+380671234567'), 'phone')
        self.assertEqual(D.detect('4111111111111111'), 'card')


class GeneratorsTest(unittest.TestCase):
    def test_generated_values_are_valid(self):
        rnd = random.Random(1)
        for _ in range(300):
            b = dt.date(1950, 1, 1) + dt.timedelta(days=rnd.randint(0, 25000))
            sex = rnd.choice('mf')
            r = D.check_rnokpp(D.make_rnokpp(b, sex, rnd))
            self.assertTrue(r['valid'])
            self.assertEqual(r['birth_date'], b.isoformat())
            self.assertEqual(r['sex'], 'чоловіча' if sex == 'm' else 'жіноча')
            self.assertTrue(D.check_edrpou(D.make_edrpou(rnd))['valid'])
            self.assertTrue(D.check_iban(D.make_iban(rnd))['valid'])
            self.assertTrue(D.check_unzr(D.make_unzr(b, rnd))['valid'])
            self.assertTrue(D.check_card(D.make_card(rnd))['valid'])
            self.assertTrue(D.check_phone(D.make_phone(rnd))['valid'])

    def test_person_is_consistent(self):
        p = D.make_person(random.Random(7), 'f', '1990-05-17')
        self.assertEqual(p['birth_date'], '1990-05-17')
        self.assertTrue(p['patronymic'].endswith('івна') or p['patronymic'].endswith('ївна'))
        self.assertEqual(D.check_rnokpp(p['rnokpp'])['birth_date'], '1990-05-17')
        self.assertTrue(p['unzr'].startswith('19900517-'))
        self.assertTrue(p['email'].endswith('@example.com'))

    def test_seed_is_reproducible(self):
        self.assertEqual(D.make_person(random.Random(42)), D.make_person(random.Random(42)))


class TranslitTest(unittest.TestCase):
    def test_official_examples(self):
        # Приклади з Постанови КМУ № 55
        cases = {'Згорани': 'Zghorany', 'Розгон': 'Rozghon', 'Юрій': 'Yurii', 'Юлія': 'Yuliia', 'Олексій': 'Oleksii',
                 'Щербухи': 'Shcherbukhy', 'Знамʼянка': 'Znamianka', "Знам'янка": 'Znamianka', 'Їжакевич': 'Yizhakevych',
                 'Кадиївка': 'Kadyivka', 'Яготин': 'Yahotyn', 'Костянтин': 'Kostiantyn', 'Ґалаґан': 'Galagan',
                 'Єнакієве': 'Yenakiieve', 'Гайова': 'Haiova', 'Короп': 'Korop', 'Суми': 'Sumy', 'Феодосія': 'Feodosiia'}
        for uk, lat in cases.items():
            with self.subTest(uk=uk):
                self.assertEqual(D.translit(uk), lat)

    def test_upper_and_slug(self):
        self.assertEqual(D.translit('ЖИТОМИР'), 'ZHYTOMYR')
        self.assertEqual(D.slugify('Київ — столиця України!'), 'kyiv-stolytsia-ukrainy')


class NumbersTest(unittest.TestCase):
    def test_words(self):
        self.assertEqual(D.number_words(0), 'нуль')
        self.assertEqual(D.number_words(21, 'f'), 'двадцять одна')
        self.assertEqual(D.number_words(2, 'n'), 'два')
        self.assertEqual(D.number_words(2022), 'дві тисячі двадцять два')
        self.assertEqual(D.number_words(1_000_000), 'один мільйон')
        self.assertEqual(D.number_words(5_011_000), 'пʼять мільйонів одинадцять тисяч')
        self.assertEqual(D.number_words(-3), 'мінус три')

    def test_amount(self):
        self.assertEqual(D.amount_words('1234.56'), 'Одна тисяча двісті тридцять чотири гривні 56 копійок')
        self.assertEqual(D.amount_words('1'), 'Одна гривня 00 копійок')
        self.assertEqual(D.amount_words('22,02', kop_words=True), 'Двадцять дві гривні дві копійки')
        self.assertEqual(D.amount_words('101', 'USD'), 'Сто один долар США 00 центів')
        self.assertEqual(D.amount_words('1', 'EUR'), 'Одне євро 00 центів')
        self.assertEqual(D.amount_words('1 000 000'), 'Один мільйон гривень 00 копійок')

    def test_plural(self):
        f = ('файл', 'файли', 'файлів')
        expect = {0: 'файлів', 1: 'файл', 2: 'файли', 4: 'файли', 5: 'файлів', 11: 'файлів', 12: 'файлів',
                  14: 'файлів', 21: 'файл', 22: 'файли', 25: 'файлів', 101: 'файл', 111: 'файлів', 1004: 'файли'}
        for n, w in expect.items():
            self.assertEqual(D.plural_form(n, *f), w, n)


if __name__ == '__main__':
    unittest.main()
