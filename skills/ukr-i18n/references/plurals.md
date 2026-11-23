# Форми множини для української

Правила CLDR для `uk`:

| Категорія | Коли | Приклади |
|---|---|---|
| `one` | закінчується на 1, крім 11 | 1, 21, 101 файл |
| `few` | закінчується на 2–4, крім 12–14 | 2, 3, 24 файли |
| `many` | 0, 5–20, закінчується на 0, 5–9, 11–14 | 0, 5, 11, 25 файлів |
| `other` | дробові | 1,5 файла |

Формула (gettext): `n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2`.

Типова помилка — правило англійської (`one`/`other`): «5 файли», «11 файл». Ще одна — забута форма `other`,
яку деякі бібліотеки вимагають завжди.

## JavaScript без бібліотек

```js
const rules = new Intl.PluralRules('uk');
const forms = { one: 'файл', few: 'файли', many: 'файлів', other: 'файла' };
const files = (n) => `${n.toLocaleString('uk-UA')} ${forms[rules.select(n)]}`;
files(1); files(3); files(11); files(1.5);   // 1 файл, 3 файли, 11 файлів, 1,5 файла
```

## i18next (v21+, формат JSON v4)

Працює «з коробки» через `Intl.PluralRules`. Потрібні всі чотири ключі:

```json
{
  "files_one": "{{count}} файл",
  "files_few": "{{count}} файли",
  "files_many": "{{count}} файлів",
  "files_other": "{{count}} файла"
}
```
`t('files', { count: 5 })` → «5 файлів». Старі версії (формат v3, `_0/_1/_2`) — переходьте на v4.

## vue-i18n (v9+)

Вбудоване правило розраховане на англійську — **для української його треба задати**:

```js
// i18n.js
function ukPlural(choice, choicesLength) {
  // 3 форми: «{n} файл | {n} файли | {n} файлів»; 4 форми: «немає файлів | {n} файл | {n} файли | {n} файлів»
  const n = Math.abs(choice);
  const base = choicesLength === 4 ? 1 : 0;
  if (base && n === 0) return 0;
  const m10 = n % 10, m100 = n % 100;
  if (!Number.isInteger(n)) return base + 1;
  if (m10 === 1 && m100 !== 11) return base;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return base + 1;
  return base + 2;
}

export const i18n = createI18n({
  locale: 'uk',
  fallbackLocale: 'en',
  pluralRules: { uk: ukPlural },
  messages,
});
```
```json
{ "files": "{n} файл | {n} файли | {n} файлів" }
```
`t('files', 5)` → «5 файлів». Nuxt i18n: те саме `pluralRules` у `i18n.config.ts` (`defineI18nConfig`).

## ICU MessageFormat (FormatJS / react-intl, Angular, Flutter ARB, Java ICU4J, Lingui)

```
{count, plural, one {# файл} few {# файли} many {# файлів} other {# файла}}
```
`other` обовʼязкова. Точні значення — `=0 {немає файлів}` перед іншими формами.
Angular: ICU-вирази в шаблонах і `$localize`; Flutter: ARB з тим самим синтаксисом, `intl` знає `uk`.

## Android

```xml
<plurals name="files">
    <item quantity="one">%d файл</item>
    <item quantity="few">%d файли</item>
    <item quantity="many">%d файлів</item>
    <item quantity="other">%d файла</item>
</plurals>
```
`resources.getQuantityString(R.plurals.files, n, n)`. Тека — `values-uk`, не `values-ua`.

## iOS / macOS

String Catalog (`.xcstrings`): «Vary by Plural» → Xcode сам покаже форми One / Few / Many / Other для
української. Старий `.stringsdict` — ключі `one`, `few`, `many`, `other` у `NSStringPluralRuleType`.
Тека — `uk.lproj`.

## gettext (.po): Python, PHP, Django, WordPress, C

```
"Language: uk\n"
"Plural-Forms: nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);\n"

msgid "%d file"
msgid_plural "%d files"
msgstr[0] "%d файл"
msgstr[1] "%d файли"
msgstr[2] "%d файлів"
```

## .NET

`.resx` не має множини. Варіанти: бібліотека SmartFormat (`{0:plural:файл|файли|файлів}` з культурою `uk-UA`),
MessageFormat.NET (ICU-синтаксис) або власна функція:

```csharp
static string Plural(long n, string one, string few, string many)
{
    n = Math.Abs(n);
    long m10 = n % 10, m100 = n % 100;
    if (m10 == 1 && m100 != 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
}
```

## Laravel

```php
// lang/uk/messages.php
'files' => ':count файл|:count файли|:count файлів',
```
`trans_choice('messages.files', $n)` — Laravel знає три форми множини для `uk`.

## Ruby on Rails

Додайте гем `rails-i18n` — він містить правила множини для `uk` (`one`, `few`, `many`, `other`):

```yaml
uk:
  files:
    one: "%{count} файл"
    few: "%{count} файли"
    many: "%{count} файлів"
    other: "%{count} файла"
```
