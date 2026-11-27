# ukr-dev-kit

Українська мова для розробників і AI-агентів: вичитка суржику й типографіки, прибирання ШІ-стилю, перевірка локалізації,
українські дані й озвучка. Без жодних залежностей, Python 3.10+.

```bash
pipx install ukr-dev-kit        # або: uv tool install ukr-dev-kit
```

| Команда | Що робить |
|---|---|
| `ukr-lint` | Вичитка: суржик, кальки, правопис 2019, лапки «ялинки», тире, апостроф, змішані латиниця й кирилиця. Markdown, JSON, YAML, PO, рядки в коді; `--fix`, `--diff origin/main`, `--format github` |
| `ukr-ai-tells` | Ознаки ШІ-стилю з урахуванням каналу (`--channel email`): Markdown і заглушки `[Імʼя]` там, де їх побачить читач, тире-зʼєднувачі, шаблонні розділи, старі штампи; ознаки людської чернетки окремо; щільність на 1000 слів, `--max-score` для CI |
| `ukr-i18n` | Перевірка українських локалей: пропущені ключі, плейсхолдери, форми множини one/few/many/other, неперекладене, код `ua` замість `uk` |
| `ukr-data` | РНОКПП, ЄДРПОУ, IBAN, УНЗР, телефони: перевірка й генерація тестових даних; транслітерація КМУ № 55; суми прописом |
| `ukr-voice` | Озвучка українською: Gemini TTS або локальний HolosTTS, пресети, діалоги, перевірка розбірливості |

```bash
ukr-lint README.md src/locales/uk.json
ukr-lint --diff origin/main --format github
ukr-i18n --auto --lint
ukr-ai-tells post.md
ukr-data check 3652504575
ukr-data amount 1234.56          # Одна тисяча двісті тридцять чотири гривні 56 копійок
ukr-voice say "Привіт!" -o hi.mp3
```

Цей самий код працює як скіли для Claude Code, Codex, Cursor та інших агентів, а також як pre-commit хуки й
GitHub Action. Повна документація, приклади й аудіо: https://github.com/MaxKarasha/ukr-dev-kit
