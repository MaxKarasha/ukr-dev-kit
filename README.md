<p align="center">
  <img src="docs/assets/banner.svg" alt="ukr-dev-kit — українська мова для AI-агентів" width="100%">
</p>

<p align="center">
  <a href="https://github.com/MaxKarasha/ukr-dev-kit/actions/workflows/ci.yml"><img src="https://github.com/MaxKarasha/ukr-dev-kit/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/ukr-dev-kit/"><img src="https://img.shields.io/pypi/v/ukr-dev-kit?label=PyPI&color=2f7bff" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/ліцензія-MIT-2f7bff" alt="Ліцензія MIT"></a>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/залежності-0-3fb950" alt="Без залежностей">
  <img src="https://img.shields.io/badge/Claude_Code-плагін-D97757?logo=claude&logoColor=white" alt="Плагін Claude Code">
  <img src="https://img.shields.io/badge/Agent_Skills-сумісно-6E56CF" alt="Agent Skills">
  <img src="https://img.shields.io/badge/зроблено_в-Україні-0057B7?labelColor=FFD500" alt="Зроблено в Україні">
</p>

<p align="center">
  <b>Пʼять скілів, з якими Claude Code, Codex, Cursor та інші агенти працюють з українською як носії:<br>
  озвучують, вичитують, пишуть без ШІ-стилю, локалізують і перевіряють українські дані.</b>
</p>

<p align="center">
  <a href="#встановлення">Встановлення</a> ·
  <a href="#ukr-voice-озвучка">Озвучка</a> ·
  <a href="#ukr-proofread-вичитка">Вичитка</a> ·
  <a href="#ukr-humanize-без-ші-стилю">Без ШІ-стилю</a> ·
  <a href="#ukr-i18n-локалізація">Локалізація</a> ·
  <a href="#ukr-data-українські-дані">Дані</a> ·
  <a href="#ci-pre-commit-і-github-action">CI</a>
</p>

---

## Навіщо

AI-агенти пишуть код блискуче, а от українська в них часто «майже правильна»:

<!-- ukr-lint-disable — нижче навмисні приклади помилок --> <!-- ukr-ai-tells-disable -->
- кнопка «Відмінити», «Настройки», «Слідуючий крок» і «прийміть участь» у текстах інтерфейсу;
- «5 файли» й «11 файл», бо плюралізацію налаштовано як для англійської;
- `ua.json` замість `uk.json`, «Пpивiт» з латинськими `p` та `i`, прямі лапки й дефіс замість тире;
- у текстах повно «варто зазначити», «відіграє ключову роль» і «це не просто X — це Y», а в листах лишаються зірочки Markdown;
- РНОКПП, ЄДРПОУ й IBAN перевіряють лише довжиною, а суму прописом пишуть уручну;
- українську озвучку роблять сторонніми сервісами або не роблять зовсім.
<!-- ukr-lint-enable --> <!-- ukr-ai-tells-enable -->

**ukr-dev-kit** дає агентові знання й інструменти, щоб це виправити: правила, словники, перевірені
алгоритми й CLI-утиліти на чистому Python без жодної залежності. Агент сам вирішує, коли їх застосувати.
Ви просто пишете «озвуч», «вичитай», «додай українську локаль» чи «згенеруй тестових клієнтів».

## Що всередині

| Скіл | Що вміє | Скажіть агентові |
|---|---|---|
| 🎙 [**ukr-voice**](skills/ukr-voice/SKILL.md) | Озвучка через Gemini TTS (хмара) або HolosTTS (офлайн): пресети, емоції, діалоги кількома голосами, перевірка розбірливості | «Озвуч цей текст для Reels голосом диктора» |
| ✍️ [**ukr-proofread**](skills/ukr-proofread/SKILL.md) | Лінтер суржику, кальок і типографіки: 140+ правил, `--fix`, лише змінені в гілці рядки | «Вичитай README й тексти інтерфейсу перед релізом» |
| 🪶 [**ukr-humanize**](skills/ukr-humanize/SKILL.md) | Прибирає ШІ-стиль, відкалібровано під моделі 2026 року: розмітка чату за каналом, тире-зʼєднувачі, шаблонні розділи, штампи; ознаки людської чернетки окремо; шар для художнього тексту | «Перепиши пост, щоб не звучав як ChatGPT» |
| 🌍 [**ukr-i18n**](skills/ukr-i18n/SKILL.md) | Плюралізація one/few/many, формати uk-UA, перевірка локалей: ключі, плейсхолдери, неперекладене | «Додай українську в застосунок і перевір uk.json» |
| 🔢 [**ukr-data**](skills/ukr-data/SKILL.md) | РНОКПП, ЄДРПОУ, IBAN, УНЗР, телефони: перевірка й генерація; транслітерація КМУ № 55; сума прописом; кличний відмінок | «Згенеруй 50 тестових клієнтів з валідними РНОКПП» |

У Claude Code є ще **хук автовичитки**: після кожного редагування української локалі чи документації
агент одразу бачить свої помилки й виправляє їх.

## Встановлення

**Claude Code.** Плагін зі скілами й хуком автовичитки:

```text
/plugin marketplace add MaxKarasha/ukr-dev-kit
/plugin install ukr-dev-kit@ukr-dev-kit
```

**Codex, Cursor, Gemini CLI, Windsurf та інші агенти.** Через відкритий CLI скілів:

```bash
npx skills add MaxKarasha/ukr-dev-kit
```

**Вручну.** Скопіюйте теки скілів туди, де ваш агент їх шукає:

```bash
git clone https://github.com/MaxKarasha/ukr-dev-kit
cp -r ukr-dev-kit/skills/* ~/.claude/skills/
```

**Без агента.** Звичайні консольні команди з PyPI:

```bash
pipx install ukr-dev-kit      # або: uv tool install ukr-dev-kit
ukr-lint --help               # також ukr-ai-tells, ukr-i18n, ukr-data, ukr-voice
```

Потрібен Python 3.10+. Для mp3 знадобиться `ffmpeg`, для локальної озвучки ще ~2 ГБ на диску.

---

## ukr-voice: озвучка

Два рушії, одна команда. З ключем Gemini звучить як живий диктор. Якщо інтернету немає або текст
конфіденційний, працює локальна модель [HolosTTS](https://github.com/patriotyk/HolosTTS).

| Послухати (клік — відкриє плеєр) | Що це |
|---|---|
| <a href="https://github.com/MaxKarasha/ukr-dev-kit/raw/main/docs/samples/narrator.mp3"><img src="docs/assets/wave-narrator.png" width="320" alt="Оповідач"></a> | **Оповідач**: пресет `оповідач`, Gemini |
| <a href="https://github.com/MaxKarasha/ukr-dev-kit/raw/main/docs/samples/promo.mp3"><img src="docs/assets/wave-promo.png" width="320" alt="Реклама"></a> | **Реклама**: пресет `реклама`, емоція й пауза з розмітки |
| <a href="https://github.com/MaxKarasha/ukr-dev-kit/raw/main/docs/samples/dialog.mp3"><img src="docs/assets/wave-dialog.png" width="320" alt="Діалог"></a> | **Діалог** двома голосами одним запитом ([сценарій](docs/samples/dialog.txt), [субтитри](docs/samples/dialog.vtt)) |
| <a href="https://github.com/MaxKarasha/ukr-dev-kit/raw/main/docs/samples/offline.mp3"><img src="docs/assets/wave-offline.png" width="320" alt="Офлайн"></a> | **Офлайн**: HolosTTS на ноутбуці, без інтернету |

```bash
ukr-voice doctor                                   # що встановлено й який рушій буде обрано
ukr-voice say "Привіт! Це перевірка." -o hi.mp3    # пресет «оповідач»
ukr-voice say "(захоплено) Нова версія вже тут! / *Швидше* й зручніше." -o ad.mp3 --preset реклама
ukr-voice dialog scene.txt -o scene.mp3 --split lines/    # діалог + кожна репліка окремо
ukr-voice audition "Вітаємо!" -o picks/ --gender f        # одна фраза різними голосами
ukr-voice check hi.mp3 --text "Привіт! Це перевірка."     # Whisper: що почуто й % збігу
ukr-voice say "…" -o reel.mp3 --subs                       # + субтитри reel.srt і reel.vtt
```

|  | Gemini TTS | HolosTTS |
|---|---|---|
| Якість | найприродніша, емоції описом | добра, рівна дикторська |
| Де працює | хмара Google, потрібен ключ | ваш компʼютер, офлайн |
| Голоси | 30 (з підказками, які пасують українській) | десятки + суміші голосів |
| Діалоги | одним запитом, голоси «чують» одне одного | по репліках |
| Вартість | безкоштовний рівень Gemini API, далі — за тарифом | безкоштовно, без лімітів |
| Налаштування | `ukr-voice setup gemini` | `ukr-voice setup holos` (~2 ГБ) |

**Що ще вміє:** 10 пресетів (оповідач, новини, реклама, казка, урок, подкаст, гід…) з налаштуваннями для
обох рушіїв; режисерська розмітка: емоції `(радісно)`, паузи `/ // ///`, логічний наголос `*слово*`,
ручний наголос `за+мок`; субтитри SRT/VTT з точним часом за словами; словник вимови для імен; кеш (повтор не коштує нічого); розбиття довгих текстів;
вирівнювання гучності до −16 LUFS; вихід у mp3, wav, ogg, m4a, flac.

## ukr-proofread: вичитка

<p align="center"><img src="docs/assets/lint-demo.svg" alt="ukr-lint знаходить суржик, змішані алфавіти й типографіку в uk.json" width="88%"></p>

```bash
ukr-lint README.md docs/ src/locales/uk.json   # файли й теки
ukr-lint --diff origin/main                     # лише рядки, змінені в гілці (для PR)
ukr-lint --staged                               # лише те, що в індексі (перед комітом)
ukr-lint --fix docs/                            # безпечні виправлення (позначені ✎)
ukr-lint --format github                        # анотації в GitHub Actions
```

- **140+ правил** у простих текстових файлах: суржик, кальки, правопис 2019, ІТ-терміни. Нове правило —
  один рядок, а правило з шаблоном заміни одразу виправляється автоматично.
- **Типографіка:** «ялинки», тире, апостроф (один на проєкт), `…`, пробіли, формат чисел і гривні.
- **Змішані алфавіти:** `Пpивiт` з латинськими літерами, російські `ы э ъ ё` в українському тексті.
- **Розуміє формати:** Markdown (пропускає код і посилання), JSON/ARB, YAML, `.po`, `.properties`, HTML/Vue,
  рядки й коментарі в коді (JS/TS, Python, C#, Java, Kotlin, Swift, Go, PHP…). JSON виправляє, не ламаючи екранування.
- **Не заважає:** пропускає URL, плейсхолдери, теги й російський текст; `.ukr-lint.json` для налаштувань;
  `ukr-lint-disable-line` і блоки `ukr-lint-disable … ukr-lint-enable`.

Агент поєднує лінтер зі своїм розумінням контексту: механічне виправляє `--fix`, суржик переписує з
правильними відмінками, а решту вичитує за [стильовим довідником](skills/ukr-proofread/references/style-guide.md)
і [ІТ-глосарієм](skills/ukr-proofread/references/it-glossary.md).

## ukr-humanize: без ШІ-стилю

```bash
ukr-ai-tells post.md                       # ознаки зі силою, номером шаблону й рядком
ukr-ai-tells letter.md --channel email     # Markdown у листі — помилка: зірочки побачить читач
ukr-ai-tells docs/ --max-score 10          # код виходу 1, якщо щільність вища (для CI)
```

<!-- ukr-ai-tells-disable -->
Сканер налаштовано на моделі 2026 року. Словникові штампи на кшталт «варто зазначити» в них майже зникли,
тому він шукає передусім те, що видає їх тепер: зірочки й решітки Markdown у листі чи пості, заглушки
`[Імʼя]`, пункти «**Назва** — пояснення», тире в кожному четвертому реченні, розділ «Висновок» з переказом
і блок «Чому обирають нас». Старі штампи й дієприслівникові хвости теж знаходить.
<!-- ukr-ai-tells-enable -->

Канал він враховує: у листі, SMS чи Instagram Markdown прибирає, а на сайті й у документі структуру лишає.
Граматичне тире («Київ — столиця») не чіпає. Дефіс замість тире, латинські літери в кириличних словах і
різні апострофи показує окремо, бо так пишуть люди, а не моделі.

Скіл переписує текст за 26 шаблонами (адаптація [humanizer](https://github.com/blader/humanizer)), звіряє
факти з оригіналом, не вигадує «живих деталей», не рубає речення на уривки й обмежується двома колами правок.
Для художнього тексту є окремий шар: наративні ознаки з [StoryScope](https://arxiv.org/abs/2604.03136) і
«недовиразність» української ШІ-прози за дослідженнями UNLP 2026.

На людських текстах (Конституція, Вікіпедія) щільність ознак нижча за 4 на 1000 слів, і CI за цим стежить.
Сканер не визначає авторство й не допомагає обходити детектори: його мета — текст, який читач сприйме як
написаний для нього. Джерела даних зібрано в [sources.md](skills/ukr-humanize/references/sources.md).

## ukr-i18n: локалізація

<p align="center"><img src="docs/assets/i18n-demo.svg" alt="ukr-i18n порівнює uk.json з en.json" width="88%"></p>

```bash
ukr-i18n --auto            # знайде всі українські локалі й порівняє з англійськими
ukr-i18n --auto --lint     # + вичитка перекладів
```

- **Формати:** i18next, vue-i18n, ICU MessageFormat (FormatJS, Angular, Flutter), gettext `.po`,
  Android `strings.xml`, iOS `.strings`, .NET `.resx`, `.properties`, YAML.
- **Знаходить:** пропущені й застарілі ключі, порожні й неперекладені значення, різні плейсхолдери й теги,
  неповні форми множини (one, few, many, other), російські літери, код `ua` замість `uk`.
- **Довідники для агента:** готові [налаштування множини](skills/ukr-i18n/references/plurals.md) для
  12 фреймворків (у vue-i18n без них буде «5 файли»), [формати uk-UA](skills/ukr-i18n/references/formats.md)
  (дати в родовому відмінку, нерозривні пробіли, сортування з Ґ, Є, І, Ї), [глосарій інтерфейсу](skills/ukr-i18n/references/ui-glossary.md).

## ukr-data: українські дані

```bash
$ ukr-data check 3652504575
РНОКПП (ІПН) 3652504575: ✔ правильний
  дата народження: 2000-01-01
  стать: чоловіча

$ ukr-data gen person --seed 7 --json
{ "full_name": "Яковенко Ірина Максимівна", "birth_date": "1966-07-01", "rnokpp": "2428809649",
  "unzr": "19660701-95486", "phone": "+380 67 851 33 58", "iban": "UA213052990000166131860913909", … }

$ ukr-data translit "Згорани, Юлія Щербак"          →  Zghorany, Yuliia Shcherbak
$ ukr-data amount 1234.56                          →  Одна тисяча двісті тридцять чотири гривні 56 копійок
$ ukr-data plural 24 файл файли файлів             →  24 файли
$ ukr-data vocative "Олена Петрівна"                →  Олено Петрівно
```

- **Перевірка з розшифровкою:** РНОКПП (дата народження, стать), ЄДРПОУ, IBAN (МФО, банк), УНЗР,
  телефон (E.164, оператор), картка (Луна).
- **Генерація тестових даних** з правильними контрольними сумами: узгоджені профілі людей
  (ПІБ з правильним по батькові, РНОКПП і УНЗР за датою народження) та компаній; `--seed` для фікстур.
- **Транслітерація** за Постановою КМУ № 55 (як у паспортах) і slug для URL.
- **Числа й суми прописом** з правильним родом: гривня, долар, євро.
- **Кличний відмінок** для звертань: «Вітаємо, Олено Петрівно!», «пане Тарасе».
- **Готові валідатори** для вашого коду: [TypeScript, Python і C#](skills/ukr-data/references/validators.md).
  Саме цей код з документації CI проганяє на тестових векторах.

## Автовичитка під час роботи агента

У плагіні Claude Code є хук: після кожного `Write`/`Edit` української локалі (`uk.json`, `values-uk`,
`uk.po`…) або українського документа агент отримує список явних помилок і виправляє їх сам. Хук мовчить,
якщо проблем немає, не чіпає російськомовні й англійські файли й ніколи не блокує роботу.
Вимкнути: `UKR_LINT_HOOK=0` або `"hook": false` у `.ukr-lint.json`.

## CI: pre-commit і GitHub Action

**pre-commit:**

```yaml
repos:
  - repo: https://github.com/MaxKarasha/ukr-dev-kit
    rev: v0.4.1
    hooks:
      - id: ukr-lint      # вичитка змінених файлів
      - id: ukr-i18n      # перевірка українських локалей
```

**GitHub Actions** з анотаціями просто в рядках PR:

```yaml
- uses: actions/checkout@v5
  with:
    fetch-depth: 0
- uses: MaxKarasha/ukr-dev-kit@v0.4.1
  with:
    level: warning      # error | warning | hint
    i18n: true
```

## Якість

- **85 модульних тестів** на Linux, macOS і Windows (Python 3.10–3.14), без мережі й залежностей.
- **Корпус грамотного тексту**: Конституція й статті Вікіпедії, ~400 тис. символів. Лінтер на ньому має
  мовчати, а сканер ШІ-стилю — показувати щільність нижчу за 6, тож правило з хибними спрацюваннями CI не пропустить.
- **Валідатори з документації** (TypeScript, Python, C#) проганяються на тестових векторах.
- **Evals** для агентів ([`evals/`](evals)): з плагіном 7/7 кейсів, без плагіна 5/7 (v0.2.0); для ukr-humanize
  по 3 запуски: лист для Gmail 3/3, допис у блог 3/3. Скіли вмикаються на своїх задачах і мовчать на чужих.
  Подробиці, зокрема невдалий запуск і що виправили, — у [RESULTS.md](evals/RESULTS.md).

## Приватність і ключі

- Вичитка, локалізація й дані працюють **повністю локально**: нічого нікуди не надсилається.
- Озвучка через Gemini надсилає текст у Google Gemini API. Для конфіденційних текстів — `--engine holos`.
- Ключ Gemini вводиться приховано у вашому терміналі (`ukr-voice setup gemini`) і зберігається з
  правами `600`; також працює змінна `GEMINI_API_KEY`. Агент ключа не бачить.
- Згенеровані РНОКПП, IBAN тощо — лише для тестів: випадковий номер може збігтися зі справжнім.

## Як це влаштовано

```text
ukr-dev-kit/
├── .claude-plugin/        # маніфест плагіна й маркетплейсу Claude Code
├── hooks/                 # хук автовичитки
├── skills/
│   ├── ukr-voice/         # SKILL.md · scripts/ (CLI, Gemini, HolosTTS) · assets/ (голоси, пресети) · references/
│   ├── ukr-proofread/     # SKILL.md · scripts/ukr_lint.py · rules/*.txt · references/
│   ├── ukr-humanize/      # SKILL.md · scripts/ukr_ai_tells.py · rules/tells.txt · references/
│   ├── ukr-i18n/          # SKILL.md · scripts/i18n_check.py · references/
│   └── ukr-data/          # SKILL.md · scripts/ukr_data.py · references/validators.md
├── src/ukr_dev_kit/       # пакет PyPI: консольні команди поверх скриптів скілів
├── tests/                 # unittest, без мережі й залежностей
├── tools/                 # перевірка структури, валідаторів, рендер демо
├── action.yml             # GitHub Action
└── .pre-commit-hooks.yaml
```

Кожен скіл самодостатній: SKILL.md з інструкціями для агента, скрипти на стандартній бібліотеці Python
і довідники, які агент читає лише за потреби.

## Плани

- [ ] Більше правил суржику й кальок від спільноти (див. нижче)
- [ ] Перевірка милозвучності у/в, і/й з урахуванням пауз і власних назв
- [ ] Локалізація форматів для Excel/Google Sheets і SQL-колацій
- [ ] Більше голосів і пресетів, клонування голосу за згодою

## Участь

Найпростіший внесок — **нове правило**: один рядок у [`skills/ukr-proofread/rules/`](skills/ukr-proofread/rules)
і тест на нього. Знайшли хибне спрацювання — це теж цінний issue.
Деталі — у [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
python3 -m unittest discover -s tests      # тести
python3 tools/validate_skills.py           # структура скілів
```

## Подяки

- Відкриті моделі й інструменти української мови від patriotyk: [HolosTTS](https://github.com/patriotyk/HolosTTS),
  [ukrainian-word-stress](https://github.com/patriotyk/ukrainian-word-stress), [ipa-uk](https://github.com/patriotyk/ipa-uk).
- Український правопис 2019, Постанова КМУ № 55 про транслітерацію, правила множини [Unicode CLDR](https://cldr.unicode.org/).
- Gemini API, з яким українська озвучка звучить природно.
- Для ukr-humanize: шаблони [humanizer](https://github.com/blader/humanizer) (Siqi Chen, MIT), каталог
  [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) (WikiProject AI Cleanup),
  виміри українських текстів [panchlab/humanizer-uk](https://github.com/panchlab/humanizer-uk) (MIT) і наративні
  ознаки з [StoryScope](https://arxiv.org/abs/2604.03136) (Russell et al., 2026).

## Ліцензія

[MIT](LICENSE). Виняток — тексти корпусу `tests/corpus/wikipedia_*.txt` (CC BY-SA 4.0, див.
[джерела](tests/corpus/README.md)). Озвучку, створену через Gemini, використовуйте відповідно до умов Google Gemini API;
HolosTTS — під ліцензією MIT від автора моделі.
