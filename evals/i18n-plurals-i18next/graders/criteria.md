---
type: llm
---
PASS if the uk.json fragment has the keys files_one, files_few, files_many (and preferably files_other) with correct forms: «{{count}} файл», «{{count}} файли», «{{count}} файлів» (other — «{{count}} файла» or similar), and keeps the {{count}} placeholder.
FAIL if it uses only one/other like English, has wrong word forms, or changes the placeholder.
