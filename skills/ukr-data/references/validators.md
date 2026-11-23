# Валідатори: TypeScript, Python, C#

Перевірені реалізації: код саме з цього файлу автоматично проганяється на тестових векторах нижче
(`tools/check_validators.py` у репозиторії ukr-dev-kit). Копіюйте разом із тестами.

## Тестові вектори

| Тип | Правильні | Неправильні |
|---|---|---|
| РНОКПП | `3652504575` (01.01.2000, чол.) | `3652504576`, `365250457` |
| ЄДРПОУ | `14360570`, `00032129`, `00135390` | `14360571` |
| IBAN | `UA213223130000026007233566001` | `UA213223130000026007233566002` |
| УНЗР | `20000101-00019`, `2000010100019` | `20000101-00011` |

## TypeScript

```ts
/** РНОКПП (ІПН): 10 цифр, контрольна — (Σ dᵢ·wᵢ mod 11) mod 10. */
export function isValidRnokpp(value: string): boolean {
  const v = value.replace(/\s/g, '');
  if (!/^\d{10}$/.test(v)) return false;
  const w = [-1, 5, 7, 9, 4, 6, 10, 5, 7];
  const sum = w.reduce((s, k, i) => s + k * Number(v[i]), 0);
  return (((sum % 11) + 11) % 11) % 10 === Number(v[9]);
}

/** Дата народження й стать з РНОКПП (без перевірки контрольної цифри). */
export function decodeRnokpp(v: string): { birthDate: Date; sex: 'male' | 'female' } {
  const birthDate = new Date(Date.UTC(1899, 11, 31 + Number(v.slice(0, 5))));
  return { birthDate, sex: Number(v[8]) % 2 ? 'male' : 'female' };
}

/** Код ЄДРПОУ: 8 цифр. */
export function isValidEdrpou(value: string): boolean {
  const v = value.replace(/\s/g, '');
  if (!/^\d{8}$/.test(v)) return false;
  const n = Number(v);
  const base = n >= 30000000 && n <= 60000000 ? [7, 1, 2, 3, 4, 5, 6] : [1, 2, 3, 4, 5, 6, 7];
  const calc = (add: number) => base.reduce((s, w, i) => s + (w + add) * Number(v[i]), 0) % 11;
  let c = calc(0);
  if (c >= 10) {
    c = calc(2);
    if (c >= 10) c = 0;
  }
  return c === Number(v[7]);
}

/** IBAN України: UA + 27 знаків, mod 97 = 1. */
export function isValidUaIban(value: string): boolean {
  const v = value.replace(/\s/g, '').toUpperCase();
  if (!/^UA\d{8}[0-9A-Z]{19}$/.test(v)) return false;
  const digits = (v.slice(4) + v.slice(0, 4)).replace(/[A-Z]/g, (c) => String(c.charCodeAt(0) - 55));
  let rem = 0;
  for (const ch of digits) rem = (rem * 10 + Number(ch)) % 97;
  return rem === 1;
}

/** УНЗР: РРРРММДД-ННННК, ваги 7-3-1, mod 10. */
export function isValidUnzr(value: string): boolean {
  const m = /^(\d{8})-?(\d{5})$/.exec(value.trim());
  if (!m) return false;
  const d = m[1] + m[2];
  const w = [7, 3, 1];
  const sum = [...d.slice(0, 12)].reduce((s, c, i) => s + Number(c) * w[i % 3], 0);
  return sum % 10 === Number(d[12]);
}

/** Телефон → E.164 (+380XXXXXXXXX) або null. */
export function normalizeUaPhone(value: string): string | null {
  let d = value.replace(/\D/g, '');
  if (d.length === 10 && d.startsWith('0')) d = '38' + d;
  else if (d.length === 11 && d.startsWith('80')) d = '3' + d;
  return /^380\d{9}$/.test(d) ? '+' + d : null;
}

/** Форма слова після числа: plural(5, ['файл', 'файли', 'файлів']) → 'файлів'. */
export function plural(n: number, [one, few, many]: [string, string, string]): string {
  const m10 = Math.abs(n) % 10, m100 = Math.abs(n) % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}
```

## Python

```python
import re

def is_valid_rnokpp(value: str) -> bool:
    v = re.sub(r'\s', '', value)
    if not re.fullmatch(r'\d{10}', v):
        return False
    s = sum(int(c) * w for c, w in zip(v, (-1, 5, 7, 9, 4, 6, 10, 5, 7)))
    return (s % 11) % 10 == int(v[9])

def is_valid_edrpou(value: str) -> bool:
    v = re.sub(r'\s', '', value)
    if not re.fullmatch(r'\d{8}', v):
        return False
    base = (7, 1, 2, 3, 4, 5, 6) if 30000000 <= int(v) <= 60000000 else (1, 2, 3, 4, 5, 6, 7)
    c = sum(int(d) * w for d, w in zip(v, base)) % 11
    if c >= 10:
        c = sum(int(d) * (w + 2) for d, w in zip(v, base)) % 11
        if c >= 10:
            c = 0
    return c == int(v[7])

def is_valid_ua_iban(value: str) -> bool:
    v = re.sub(r'\s', '', value).upper()
    if not re.fullmatch(r'UA\d{8}[0-9A-Z]{19}', v):
        return False
    return int(''.join(str(int(c, 36)) for c in v[4:] + v[:4])) % 97 == 1

def is_valid_unzr(value: str) -> bool:
    m = re.fullmatch(r'(\d{8})-?(\d{5})', value.strip())
    if not m:
        return False
    d = m.group(1) + m.group(2)
    return sum(int(c) * (7, 3, 1)[i % 3] for i, c in enumerate(d[:12])) % 10 == int(d[12])
```

## C#

```csharp
using System.Linq;
using System.Numerics;
using System.Text.RegularExpressions;

public static class UaValidators
{
    public static bool IsValidRnokpp(string value)
    {
        var v = Regex.Replace(value ?? "", @"\s", "");
        if (!Regex.IsMatch(v, @"^\d{10}$")) return false;
        int[] w = { -1, 5, 7, 9, 4, 6, 10, 5, 7 };
        int sum = w.Select((k, i) => k * (v[i] - '0')).Sum();
        return ((sum % 11 + 11) % 11) % 10 == v[9] - '0';
    }

    public static bool IsValidEdrpou(string value)
    {
        var v = Regex.Replace(value ?? "", @"\s", "");
        if (!Regex.IsMatch(v, @"^\d{8}$")) return false;
        long n = long.Parse(v);
        int[] b = n >= 30000000 && n <= 60000000 ? new[] { 7, 1, 2, 3, 4, 5, 6 } : new[] { 1, 2, 3, 4, 5, 6, 7 };
        int Calc(int add) => b.Select((w, i) => (w + add) * (v[i] - '0')).Sum() % 11;
        int c = Calc(0);
        if (c >= 10) { c = Calc(2); if (c >= 10) c = 0; }
        return c == v[7] - '0';
    }

    public static bool IsValidUaIban(string value)
    {
        var v = Regex.Replace(value ?? "", @"\s", "").ToUpperInvariant();
        if (!Regex.IsMatch(v, @"^UA\d{8}[0-9A-Z]{19}$")) return false;
        var digits = string.Concat((v[4..] + v[..4]).Select(c => char.IsLetter(c) ? (c - 55).ToString() : c.ToString()));
        return BigInteger.Parse(digits) % 97 == 1;
    }

    public static bool IsValidUnzr(string value)
    {
        var m = Regex.Match((value ?? "").Trim(), @"^(\d{8})-?(\d{5})$");
        if (!m.Success) return false;
        var d = m.Groups[1].Value + m.Groups[2].Value;
        int[] w = { 7, 3, 1 };
        return Enumerable.Range(0, 12).Sum(i => (d[i] - '0') * w[i % 3]) % 10 == d[12] - '0';
    }
}
```

## Чого не робити

- Не перевіряйте РНОКПП лише довжиною — контрольна цифра відсіює більшість описок.
- Не відкидайте РНОКПП, що починаються з 0, — тримайте їх рядком, не числом (те саме для ЄДРПОУ `00032129`).
- Не шукайте в РНОКПП «приховані» дані, крім дати й статі, і не показуйте їх без потреби —
  це персональні дані.
- Людина без РНОКПП (відмова з релігійних переконань) має в паспорті відмітку — передбачте поле
  «серія й номер паспорта» як альтернативу.
