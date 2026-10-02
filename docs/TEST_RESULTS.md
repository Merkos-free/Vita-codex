# Фактически выполненные проверки

2026-10-03, Linux, Python 3.13.5, g++ 14.2.0.

Исходный архив: 39 Python tests, OK. Обновлённая версия: **55 Python tests, OK**, 5.439 секунды. Полный вывод — test-run.txt. C++17 с -Wall -Wextra -Werror -pedantic: **35 grouped checks passed**.

Проверки включают подставной JSONL Codex, ограничения операций, PIN/tokens, approvals, timeout без повтора, HTTP и настоящий loopback TLS с временным сертификатом, PCM/WAV, Unicode, UI model. Новые 16 тестов проверяют Windows launcher layout (временные файлы, НЕ настоящий Windows runtime), отказ batch/shell, field-scoped schema и консервативные разрешения.

Не выполнялись модельные запросы, чтение аккаунта владельца, Windows runtime, cross-compile, настоящий рендерер/IME/микрофон Vita, native HTTPS и диктовка. CI на GitHub имеет отдельный статус на странице проверки коммита; этот отчёт не подменяет его.
