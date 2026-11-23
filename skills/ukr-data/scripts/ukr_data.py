#!/usr/bin/env python3
"""ukr-data — українські дані для розробників: перевірка, генерація тестових значень, транслітерація,
числа й суми прописом. Лише стандартна бібліотека Python 3.9+.

    ukr_data.py check 3652504575                 # тип визначається сам: РНОКПП, ЄДРПОУ, IBAN, УНЗР, телефон, картка
    ukr_data.py check UA213223130000026007233566001 --json
    ukr_data.py gen rnokpp -n 5 --sex f --birth 1990-05-17
    ukr_data.py gen person -n 3 --json           # узгоджений профіль: ПІБ, стать, дата, РНОКПП, УНЗР, телефон, IBAN
    ukr_data.py gen company | edrpou | iban | unzr | phone | card
    ukr_data.py translit "Згорани, Юлія Щербак" [--slug]   # офіційна транслітерація (Постанова КМУ № 55)
    ukr_data.py words 2021 [--gender f|n]        # дві тисячі двадцять один
    ukr_data.py amount 1234.56 [--currency UAH|USD|EUR] [--kop-words]
    ukr_data.py plural 21 файл файли файлів      # 21 файл

Генеровані значення мають правильні контрольні суми, але придатні ЛИШЕ для тестів:
випадковий номер може збігтися з чиїмось справжнім.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import sys
from typing import Optional

__version__ = '0.1.0'
APOS = 'ʼ'

# ════════════════════════════════════ контрольні суми ════════════════════════════════════
RNOKPP_W = (-1, 5, 7, 9, 4, 6, 10, 5, 7)
RNOKPP_BASE = dt.date(1899, 12, 31)


def rnokpp_check_digit(d9: str) -> int:
    s = sum(int(c) * w for c, w in zip(d9, RNOKPP_W))
    return (s % 11) % 10          # у Python % завжди невідʼємний


def check_rnokpp(v: str) -> dict:
    """РНОКПП (ІПН) фізичної особи: 10 цифр. Перші 5 — днів від 31.12.1899 до дати народження,
    9-та — стать (непарна — чоловіча), 10-та — контрольна."""
    v = re.sub(r'\s', '', v)
    if not re.fullmatch(r'\d{10}', v):
        return _bad('rnokpp', v, 'РНОКПП — рівно 10 цифр')
    if rnokpp_check_digit(v[:9]) != int(v[9]):
        return _bad('rnokpp', v, f'неправильна контрольна цифра (має бути {rnokpp_check_digit(v[:9])})')
    birth = RNOKPP_BASE + dt.timedelta(days=int(v[:5]))
    return {'type': 'rnokpp', 'value': v, 'valid': True, 'birth_date': birth.isoformat(),
            'sex': 'чоловіча' if int(v[8]) % 2 else 'жіноча'}


def make_rnokpp(birth: dt.date, sex: str, rnd: random.Random) -> str:
    days = (birth - RNOKPP_BASE).days
    if not 1 <= days <= 99999:
        raise ValueError('дата народження поза діапазоном РНОКПП (1900–2173)')
    serial = f'{rnd.randint(0, 999):03d}'
    g = rnd.choice('13579' if sex == 'm' else '02468')
    d9 = f'{days:05d}{serial}{g}'
    return d9 + str(rnokpp_check_digit(d9))


def edrpou_check_digit(d7: str) -> int:
    n = int(d7 + '0')
    base = (7, 1, 2, 3, 4, 5, 6) if 30000000 <= n <= 60000000 else (1, 2, 3, 4, 5, 6, 7)
    s = sum(int(c) * w for c, w in zip(d7, base)) % 11
    if s >= 10:
        s = sum(int(c) * (w + 2) for c, w in zip(d7, base)) % 11
        if s >= 10:
            s = 0
    return s


def check_edrpou(v: str) -> dict:
    """Код ЄДРПОУ юридичної особи: 8 цифр, остання — контрольна (ваги 1…7 або 7,1…6 залежно від діапазону)."""
    v = re.sub(r'\s', '', v)
    if not re.fullmatch(r'\d{8}', v):
        return _bad('edrpou', v, 'код ЄДРПОУ — рівно 8 цифр')
    exp = edrpou_check_digit(v[:7])
    if exp != int(v[7]):
        return _bad('edrpou', v, f'неправильна контрольна цифра (має бути {exp})')
    return {'type': 'edrpou', 'value': v, 'valid': True}


def make_edrpou(rnd: random.Random) -> str:
    d7 = f'{rnd.randint(1000000, 4499999):07d}'
    return d7 + str(edrpou_check_digit(d7))


BANKS = {  # МФО → банк (довідково, найбільші банки)
    '305299': 'ПриватБанк', '300465': 'Ощадбанк', '322001': 'Універсал Банк (monobank)', '334851': 'ПУМБ',
    '380805': 'Райффайзен Банк', '307770': 'А-Банк', '320478': 'Укргазбанк', '322313': 'Укрексімбанк',
    '300346': 'Сенс Банк', '300528': 'ОТП Банк', '300614': 'Креді Агріколь Банк', '351005': 'Укрсиббанк',
}


def _iban_num(s: str) -> int:
    return int(''.join(str(int(c, 36)) for c in s))


def check_iban(v: str) -> dict:
    """IBAN України: UA + 2 контрольні цифри + 6 цифр МФО банку + 19 знаків рахунку (усього 29)."""
    v = re.sub(r'\s', '', v).upper()
    if not v.startswith('UA'):
        return _bad('iban', v, 'український IBAN починається з UA')
    if not re.fullmatch(r'UA\d{8}[0-9A-Z]{19}', v):
        return _bad('iban', v, 'формат: UA + 27 знаків (29 загалом)')
    if _iban_num(v[4:] + v[:4]) % 97 != 1:
        return _bad('iban', v, 'неправильні контрольні цифри (mod 97)')
    mfo = v[4:10]
    res = {'type': 'iban', 'value': v, 'valid': True, 'formatted': ' '.join(v[i:i + 4] for i in range(0, 29, 4)),
           'mfo': mfo, 'account': v[10:].lstrip('0') or '0'}
    if mfo in BANKS:
        res['bank'] = BANKS[mfo]
    return res


def make_iban(rnd: random.Random, mfo: Optional[str] = None) -> str:
    mfo = mfo or rnd.choice(list(BANKS))
    acc = '0000' + ''.join(rnd.choice('0123456789') for _ in range(15))
    bban = mfo + acc
    kk = 98 - _iban_num(bban + 'UA00') % 97
    return f'UA{kk:02d}{bban}'


def unzr_check_digit(d12: str) -> int:
    w = (7, 3, 1)
    return sum(int(c) * w[i % 3] for i, c in enumerate(d12)) % 10


def check_unzr(v: str) -> dict:
    """УНЗР (запис у Єдиному демографічному реєстрі): РРРРММДД-ННННК — дата народження, номер запису,
    контрольна цифра за методом машинозчитуваної зони документів (ваги 7, 3, 1; mod 10)."""
    s = v.strip()
    m = re.fullmatch(r'(\d{8})-?(\d{5})', s)
    if not m:
        return _bad('unzr', s, 'формат УНЗР: РРРРММДД-ННННК (13 цифр)')
    d = m.group(1) + m.group(2)
    try:
        birth = dt.datetime.strptime(m.group(1), '%Y%m%d').date()
    except ValueError:
        return _bad('unzr', s, 'перші 8 цифр — не дата')
    if unzr_check_digit(d[:12]) != int(d[12]):
        return _bad('unzr', s, f'неправильна контрольна цифра (має бути {unzr_check_digit(d[:12])})')
    return {'type': 'unzr', 'value': f'{m.group(1)}-{m.group(2)}', 'valid': True, 'birth_date': birth.isoformat()}


def make_unzr(birth: dt.date, rnd: random.Random) -> str:
    d12 = birth.strftime('%Y%m%d') + f'{rnd.randint(0, 9999):04d}'
    return f'{d12[:8]}-{d12[8:]}{unzr_check_digit(d12)}'


def luhn_ok(n: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(n)):
        x = int(c) * (2 if i % 2 else 1)
        total += x - 9 if x > 9 else x
    return total % 10 == 0


def check_card(v: str) -> dict:
    v = re.sub(r'[\s-]', '', v)
    if not re.fullmatch(r'\d{13,19}', v):
        return _bad('card', v, 'номер картки — 13–19 цифр')
    if not luhn_ok(v):
        return _bad('card', v, 'не проходить перевірку Луна')
    system = {'4': 'Visa', '5': 'Mastercard', '2': 'Mastercard', '9': 'ПРОСТІР'}.get(v[0], 'інша')
    return {'type': 'card', 'value': v, 'valid': True, 'system': system,
            'masked': v[:6] + '*' * (len(v) - 10) + v[-4:]}


def make_card(rnd: random.Random) -> str:
    body = rnd.choice(['4', '5']) + ''.join(rnd.choice('0123456789') for _ in range(14))
    for d in '0123456789':
        if luhn_ok(body + d):
            return body + d
    raise AssertionError


OPERATORS = {
    '39': 'Київстар', '67': 'Київстар', '68': 'Київстар', '77': 'Київстар', '96': 'Київстар', '97': 'Київстар',
    '98': 'Київстар', '50': 'Vodafone', '66': 'Vodafone', '75': 'Vodafone', '95': 'Vodafone', '99': 'Vodafone',
    '63': 'lifecell', '73': 'lifecell', '93': 'lifecell', '91': '3Mob', '92': 'PEOPLEnet', '94': 'Інтертелеком',
}


def check_phone(v: str) -> dict:
    """Український номер: +380 XX XXX XX XX. Приймає 0XXXXXXXXX, 380…, +38 (0XX) … тощо."""
    digits = re.sub(r'\D', '', v)
    if len(digits) == 10 and digits.startswith('0'):
        digits = '38' + digits
    elif len(digits) == 11 and digits.startswith('80'):
        digits = '3' + digits
    if not re.fullmatch(r'380\d{9}', digits):
        return _bad('phone', v, 'український номер: +380 і 9 цифр')
    code = digits[3:5]
    e164 = '+' + digits
    res = {'type': 'phone', 'value': v, 'valid': True, 'e164': e164,
           'formatted': f'+380 {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:12]}'}
    if code in OPERATORS:
        res['operator'] = OPERATORS[code]
        res['kind'] = 'мобільний'
    else:
        res['kind'] = 'стаціонарний або інший'
    return res


def make_phone(rnd: random.Random) -> str:
    code = rnd.choice(list(OPERATORS))
    n = f'{rnd.randint(0, 9999999):07d}'
    return f'+380 {code} {n[:3]} {n[3:5]} {n[5:]}'


def _bad(t: str, v: str, why: str) -> dict:
    return {'type': t, 'value': v, 'valid': False, 'error': why}


CHECKERS = {'rnokpp': check_rnokpp, 'edrpou': check_edrpou, 'iban': check_iban, 'unzr': check_unzr,
            'phone': check_phone, 'card': check_card}
TYPE_UK = {'rnokpp': 'РНОКПП (ІПН)', 'edrpou': 'ЄДРПОУ', 'iban': 'IBAN', 'unzr': 'УНЗР', 'phone': 'телефон',
           'card': 'банківська картка'}


def detect(v: str) -> str:
    s = re.sub(r'[\s()-]', '', v)
    if s.upper().startswith('UA'):
        return 'iban'
    if s.startswith('+') or (s.startswith('380') and len(s) == 12) or (len(s) == 10 and s.startswith('0')):
        return 'phone'
    if re.fullmatch(r'\d{8}-?\d{5}', v.strip()) and v.strip()[:2] in ('19', '20'):
        return 'unzr'
    if re.fullmatch(r'\d{10}', s):
        return 'rnokpp'
    if re.fullmatch(r'\d{8}', s):
        return 'edrpou'
    if re.fullmatch(r'\d{13,19}', s):
        return 'unzr' if len(s) == 13 and s[:2] in ('19', '20') else 'card'
    return ''


# ════════════════════════════════════ транслітерація (КМУ № 55, 2010) ════════════════════════════════════
_TR = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e', 'є': 'ie', 'ж': 'zh', 'з': 'z',
       'и': 'y', 'і': 'i', 'ї': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p',
       'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh',
       'щ': 'shch', 'ь': '', 'ю': 'iu', 'я': 'ia'}
_TR_START = {'є': 'ye', 'ї': 'yi', 'й': 'y', 'ю': 'yu', 'я': 'ya'}
_APOS_CHARS = "ʼ’'`‘"


def translit(text: str) -> str:
    """Офіційна транслітерація українського алфавіту латиницею (Постанова КМУ від 27.01.2010 № 55):
    паспорти, документи, назви. «Зг» → «Zgh», «є/ї/й/ю/я» на початку слова → «Ye/Yi/Y/Yu/Ya»,
    ь та апостроф не передаються."""
    out = []
    for m in re.finditer(f"[А-Яа-яІіЇїЄєҐґ{_APOS_CHARS}]+|[^А-Яа-яІіЇїЄєҐґ{_APOS_CHARS}]+", text):
        w = m.group()
        if not re.match('[А-Яа-яІіЇїЄєҐґ]', w):
            out.append(w)
            continue
        res = []
        letters = w.replace("'", '').replace('ʼ', '').replace('’', '').replace('`', '').replace('‘', '')
        upper_word = letters.isupper() and len(letters) > 1
        for i, ch in enumerate(letters):
            lo = ch.lower()
            if i == 0 and lo in _TR_START:
                t = _TR_START[lo]
            elif lo == 'г' and i > 0 and letters[i - 1].lower() == 'з':
                t = 'gh'
            else:
                t = _TR.get(lo, ch)
            if ch.isupper() and t:
                t = t.upper() if upper_word else t[0].upper() + t[1:]
            res.append(t)
        out.append(''.join(res))
    return ''.join(out)


def slugify(text: str) -> str:
    s = translit(text).lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


# ════════════════════════════════════ числа прописом ════════════════════════════════════
_UNITS = {
    'm': ['нуль', 'один', 'два', 'три', 'чотири', 'пʼять', 'шість', 'сім', 'вісім', 'девʼять'],
    'f': ['нуль', 'одна', 'дві', 'три', 'чотири', 'пʼять', 'шість', 'сім', 'вісім', 'девʼять'],
    'n': ['нуль', 'одне', 'два', 'три', 'чотири', 'пʼять', 'шість', 'сім', 'вісім', 'девʼять'],
}
_TEENS = ['десять', 'одинадцять', 'дванадцять', 'тринадцять', 'чотирнадцять', 'пʼятнадцять', 'шістнадцять',
          'сімнадцять', 'вісімнадцять', 'девʼятнадцять']
_TENS = ['', '', 'двадцять', 'тридцять', 'сорок', 'пʼятдесят', 'шістдесят', 'сімдесят', 'вісімдесят', 'девʼяносто']
_HUNDREDS = ['', 'сто', 'двісті', 'триста', 'чотириста', 'пʼятсот', 'шістсот', 'сімсот', 'вісімсот', 'девʼятсот']
_SCALES = [  # (рід, one, few, many)
    ('f', 'тисяча', 'тисячі', 'тисяч'),
    ('m', 'мільйон', 'мільйони', 'мільйонів'),
    ('m', 'мільярд', 'мільярди', 'мільярдів'),
    ('m', 'трильйон', 'трильйони', 'трильйонів'),
]


def plural_form(n: int, one: str, few: str, many: str) -> str:
    """Форма слова після числа за правилами CLDR для uk (one / few / many)."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _triple(n: int, gender: str) -> list:
    words = []
    h, rest = divmod(n, 100)
    if h:
        words.append(_HUNDREDS[h])
    if 10 <= rest < 20:
        words.append(_TEENS[rest - 10])
    else:
        t, u = divmod(rest, 10)
        if t:
            words.append(_TENS[t])
        if u:
            words.append(_UNITS[gender][u])
    return words


def number_words(n: int, gender: str = 'm') -> str:
    """Кількісний числівник у називному відмінку: 2021 → «дві тисячі двадцять один».
    gender — рід іменника, що йде після числа: m (файл), f (гривня), n (євро)."""
    if n == 0:
        return 'нуль'
    if n < 0:
        return 'мінус ' + number_words(-n, gender)
    if n >= 10 ** 15:
        raise ValueError('число завелике (до 10¹⁵)')
    groups = []
    while n:
        n, r = divmod(n, 1000)
        groups.append(r)
    words = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if not g:
            continue
        if i == 0:
            words += _triple(g, gender)
        else:
            sg, one, few, many = _SCALES[i - 1]
            words += _triple(g, sg) + [plural_form(g, one, few, many)]
    return ' '.join(words)


CURRENCIES = {
    'UAH': ('f', ('гривня', 'гривні', 'гривень'), 'f', ('копійка', 'копійки', 'копійок')),
    'USD': ('m', ('долар США', 'долари США', 'доларів США'), 'm', ('цент', 'центи', 'центів')),
    'EUR': ('n', ('євро', 'євро', 'євро'), 'm', ('цент', 'центи', 'центів')),
}


def amount_words(value: str, currency: str = 'UAH', kop_words: bool = False, capital: bool = True) -> str:
    """Сума прописом для рахунків і договорів: «Одна тисяча двісті тридцять чотири гривні 56 копійок».
    Число приймається як рядок, щоб не втрачати копійки на округленні float."""
    v = value.strip().replace(' ', '').replace(' ', '').replace(',', '.')
    if not re.fullmatch(r'-?\d+(\.\d{1,2})?', v):
        raise ValueError(f'не схоже на суму: {value!r}')
    neg = v.startswith('-')
    whole, _, frac = v.lstrip('-').partition('.')
    whole, kop = int(whole), int((frac + '00')[:2])
    g1, f1, g2, f2 = CURRENCIES[currency.upper()]
    text = number_words(whole, g1) + ' ' + plural_form(whole, *f1)
    kop_text = number_words(kop, g2) if kop_words else f'{kop:02d}'
    text += f' {kop_text} {plural_form(kop, *f2)}'
    if neg:
        text = 'мінус ' + text
    return text[0].upper() + text[1:] if capital else text


# ════════════════════════════════════ тестові люди й компанії ════════════════════════════════════
MALE = {  # імʼя → (по батькові чол., жін.)
    'Олександр': ('Олександрович', 'Олександрівна'), 'Андрій': ('Андрійович', 'Андріївна'),
    'Сергій': ('Сергійович', 'Сергіївна'), 'Дмитро': ('Дмитрович', 'Дмитрівна'),
    'Максим': ('Максимович', 'Максимівна'), 'Тарас': ('Тарасович', 'Тарасівна'),
    'Іван': ('Іванович', 'Іванівна'), 'Петро': ('Петрович', 'Петрівна'), 'Микола': ('Миколайович', 'Миколаївна'),
    'Василь': ('Васильович', 'Василівна'), 'Юрій': ('Юрійович', 'Юріївна'), 'Богдан': ('Богданович', 'Богданівна'),
    'Ярослав': ('Ярославович', 'Ярославівна'), 'Олег': ('Олегович', 'Олегівна'), 'Павло': ('Павлович', 'Павлівна'),
    'Михайло': ('Михайлович', 'Михайлівна'), 'Віктор': ('Вікторович', 'Вікторівна'), 'Роман': ('Романович', 'Романівна'),
    'Ігор': ('Ігорович', 'Ігорівна'), 'Остап': ('Остапович', 'Остапівна'), 'Назар': ('Назарович', 'Назарівна'),
    'Степан': ('Степанович', 'Степанівна'), 'Григорій': ('Григорович', 'Григорівна'), 'Євген': ('Євгенович', 'Євгенівна'),
}
FEMALE = ['Олена', 'Ірина', 'Наталія', 'Оксана', 'Тетяна', 'Юлія', 'Марія', 'Анна', 'Катерина', 'Христина',
          'Соломія', 'Дарина', 'Вікторія', 'Софія', 'Олеся', 'Галина', 'Людмила', 'Ярина', 'Мирослава', 'Леся']
SURNAMES = [  # (чол., жін.)
    ('Шевченко', 'Шевченко'), ('Коваленко', 'Коваленко'), ('Бондаренко', 'Бондаренко'), ('Ткаченко', 'Ткаченко'),
    ('Кравчук', 'Кравчук'), ('Мельник', 'Мельник'), ('Савчук', 'Савчук'), ('Ковальчук', 'Ковальчук'),
    ('Поліщук', 'Поліщук'), ('Лисенко', 'Лисенко'), ('Гончар', 'Гончар'), ('Петрук', 'Петрук'),
    ('Яковенко', 'Яковенко'), ('Олійник', 'Олійник'), ('Марченко', 'Марченко'), ('Руденко', 'Руденко'),
    ('Левицький', 'Левицька'), ('Грушевський', 'Грушевська'), ('Січинський', 'Січинська'),
    ('Заболотний', 'Заболотна'), ('Литвиненко', 'Литвиненко'), ('Зінченко', 'Зінченко'), ('Гнатюк', 'Гнатюк'),
    ('Стельмах', 'Стельмах'), ('Довженко', 'Довженко'), ('Франко', 'Франко'), ('Костенко', 'Костенко'),
]
CITIES = ['Київ', 'Львів', 'Харків', 'Одеса', 'Дніпро', 'Запоріжжя', 'Вінниця', 'Полтава', 'Чернігів',
          'Івано-Франківськ', 'Ужгород', 'Тернопіль', 'Житомир', 'Рівне', 'Луцьк', 'Черкаси', 'Суми', 'Миколаїв']
COMPANY_A = ['Рідна', 'Нова', 'Перша', 'Сонячна', 'Степова', 'Карпатська', 'Дніпровська', 'Золота', 'Зелена', 'Ясна']
COMPANY_B = ['Нива', 'Хвиля', 'Гавань', 'Криниця', 'Майстерня', 'Пекарня', 'Логістика', 'Енергія', 'Оселя', 'Ланка']
FORMS = ['ТОВ', 'ПрАТ', 'ПП', 'ТДВ']


def _birth(rnd: random.Random, given: Optional[str]) -> dt.date:
    if given:
        return dt.date.fromisoformat(given)
    start, end = dt.date(1960, 1, 1), dt.date(2005, 12, 31)
    return start + dt.timedelta(days=rnd.randint(0, (end - start).days))


def make_person(rnd: random.Random, sex: Optional[str] = None, birth: Optional[str] = None) -> dict:
    sex = sex or rnd.choice('mf')
    father = rnd.choice(list(MALE))
    sur = rnd.choice(SURNAMES)
    if sex == 'm':
        name, patr, surname = rnd.choice(list(MALE)), MALE[father][0], sur[0]
    else:
        name, patr, surname = rnd.choice(FEMALE), MALE[father][1], sur[1]
    b = _birth(rnd, birth)
    email = f'{slugify(name)}.{slugify(surname)}{rnd.randint(1, 99)}@example.com'.replace('-', '')
    return {'surname': surname, 'name': name, 'patronymic': patr, 'full_name': f'{surname} {name} {patr}',
            'sex': 'чоловіча' if sex == 'm' else 'жіноча', 'birth_date': b.isoformat(),
            'rnokpp': make_rnokpp(b, sex, rnd), 'unzr': make_unzr(b, rnd), 'phone': make_phone(rnd),
            'email': email, 'city': rnd.choice(CITIES), 'iban': make_iban(rnd),
            'name_latin': f'{translit(name)} {translit(surname)}'}


def make_company(rnd: random.Random) -> dict:
    name = f'{rnd.choice(FORMS)} «{rnd.choice(COMPANY_A)} {rnd.choice(COMPANY_B).lower()}»'
    return {'name': name, 'edrpou': make_edrpou(rnd), 'iban': make_iban(rnd), 'city': rnd.choice(CITIES),
            'phone': make_phone(rnd)}


# ════════════════════════════════════ CLI ════════════════════════════════════
def _print_check(r: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    head = f'{TYPE_UK.get(r["type"], r["type"])} {r["value"]}: '
    if not r['valid']:
        print(head + '✖ ' + r['error'])
        return
    extra = {k: v for k, v in r.items() if k not in ('type', 'value', 'valid')}
    labels = {'birth_date': 'дата народження', 'sex': 'стать', 'formatted': 'формат', 'mfo': 'МФО', 'bank': 'банк',
              'account': 'рахунок', 'e164': 'E.164', 'operator': 'оператор', 'kind': 'тип', 'system': 'система',
              'masked': 'маска'}
    print(head + '✔ правильний' + ''.join(f'\n  {labels.get(k, k)}: {v}' for k, v in extra.items()))


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog='ukr-data', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('check', help='перевірити номер')
    s.add_argument('values', nargs='+')
    s.add_argument('--type', choices=list(CHECKERS))
    s.add_argument('--json', action='store_true')
    s = sub.add_parser('gen', help='згенерувати тестові дані')
    s.add_argument('kind', choices=['rnokpp', 'edrpou', 'iban', 'unzr', 'phone', 'card', 'person', 'company'])
    s.add_argument('-n', type=int, default=1)
    s.add_argument('--seed', type=int)
    s.add_argument('--sex', choices=['m', 'f'])
    s.add_argument('--birth', help='дата народження РРРР-ММ-ДД')
    s.add_argument('--mfo', help='МФО банку для IBAN')
    s.add_argument('--json', action='store_true')
    s = sub.add_parser('translit', help='транслітерація латиницею (КМУ № 55)')
    s.add_argument('text', nargs='+')
    s.add_argument('--slug', action='store_true', help='для адрес: малими, через дефіс')
    s = sub.add_parser('words', help='число прописом')
    s.add_argument('number', type=int)
    s.add_argument('--gender', choices=['m', 'f', 'n'], default='m')
    s = sub.add_parser('amount', help='сума прописом')
    s.add_argument('value')
    s.add_argument('--currency', default='UAH', choices=list(CURRENCIES))
    s.add_argument('--kop-words', action='store_true', help='копійки теж словами')
    s.add_argument('--lower', action='store_true')
    s = sub.add_parser('plural', help='форма слова після числа')
    s.add_argument('n', type=int)
    s.add_argument('forms', nargs=3, metavar=('ONE', 'FEW', 'MANY'))
    ap.add_argument('--apostrophe', default='ʼ', help='апостроф у словах на кшталт «пʼять» (типово ʼ)')
    ap.add_argument('--version', action='version', version=f'ukr-data {__version__}')
    a = ap.parse_args(argv)

    def out(s: str) -> None:
        print(s.replace('ʼ', a.apostrophe))

    if a.cmd == 'check':
        bad = 0
        for v in a.values:
            t = a.type or detect(v)
            if not t:
                r = _bad('?', v, 'не вдалося визначити тип; вкажіть --type')
            else:
                r = CHECKERS[t](v)
            bad += not r['valid']
            _print_check(r, a.json)
        return 1 if bad else 0
    if a.cmd == 'gen':
        rnd = random.Random(a.seed)
        items = []
        for _ in range(a.n):
            if a.kind == 'person':
                items.append(make_person(rnd, a.sex, a.birth))
            elif a.kind == 'company':
                items.append(make_company(rnd))
            elif a.kind == 'rnokpp':
                items.append(make_rnokpp(_birth(rnd, a.birth), a.sex or rnd.choice('mf'), rnd))
            elif a.kind == 'unzr':
                items.append(make_unzr(_birth(rnd, a.birth), rnd))
            elif a.kind == 'edrpou':
                items.append(make_edrpou(rnd))
            elif a.kind == 'iban':
                items.append(make_iban(rnd, a.mfo))
            elif a.kind == 'phone':
                items.append(make_phone(rnd))
            elif a.kind == 'card':
                items.append(make_card(rnd))
        if a.json:
            print(json.dumps(items if a.n > 1 else items[0], ensure_ascii=False, indent=2))
        else:
            for it in items:
                if isinstance(it, dict):
                    print('  '.join(f'{v}' for v in it.values()))
                else:
                    print(it)
        return 0
    if a.cmd == 'translit':
        text = ' '.join(a.text)
        print(slugify(text) if a.slug else translit(text))
        return 0
    if a.cmd == 'words':
        out(number_words(a.number, a.gender))
        return 0
    if a.cmd == 'amount':
        try:
            out(amount_words(a.value, a.currency, a.kop_words, not a.lower))
        except ValueError as e:
            print(f'ukr-data: {e}', file=sys.stderr)
            return 2
        return 0
    if a.cmd == 'plural':
        print(f'{a.n} {plural_form(a.n, *a.forms)}')
        return 0
    return 2


if __name__ == '__main__':
    sys.exit(main())
