# Evals

Перевіряють, що агент вмикає потрібний скіл і дає правильну відповідь, а на чужих задачах скіли мовчать.
Формат — [`claude plugin eval`](https://code.claude.com/docs/en/plugin-evals).

```bash
# усі кейси, з плагіном і без (порівняння), скрипти скілів дозволено запускати
claude plugin eval . --allow-tools "Bash(python3 *)" -j 4

# швидка ітерація по одному кейсу
claude plugin eval . --case data-rnokpp --runs 1 --ablation none --allow-tools "Bash(python3 *)"
```

| Кейс | Що перевіряє |
|---|---|
| `proofread-ui-texts` | вичитка текстів інтерфейсу: суржик, кальки, типографіка |
| `proofread-english-ignored` | негативний: англійський текст не вмикає українські скіли |
| `humanize-blog-post` | прибирання ШІ-стилю з абзацу без втрати фактів |
| `i18n-plurals-i18next` | форми множини one/few/many/other для i18next |
| `data-rnokpp` | перевірка РНОКПП і розшифровка дати народження |
| `data-amount-words` | сума прописом з правильним родом |
| `data-vocative` | кличний відмінок у звертанні |
| `voice-getting-started` | вибір рушія й голосу для озвучки |

Результати останнього прогону — у [RESULTS.md](RESULTS.md).
