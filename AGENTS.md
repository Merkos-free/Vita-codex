# Codex Vita: инструкции разработчику

Прочитать README.md, docs/STATUS.md, docs/ROADMAP.md, docs/VOICE.md, SECURITY.md.
Работать только в `Merkos-free/Vita-codex`. Владелец создал этот репозиторий публичным. Не менять видимость, не трогать другие проекты, не force-push. Изменения через отдельные ветки и PR; не публиковать секреты, аудио, auth.json или личные настройки.

## Непересматриваемые требования

- Нативный UI Vita; не заменять его браузером/удалённым рабочим столом/терминалом без решения владельца.
- Codex на компьютере с ChatGPT-login. Не отправлять credentials на Vita и не переиспользовать внутренние токены через самодельные HTTP endpoints.
- Голос только через встроенную функцию Codex. Нет платной API-подмены, Whisper, локальной модели или иного провайдера без нового решения владельца.
- Наличие audio/realtime в схеме не доказывает доступность Dictate или отсутствие дополнительных начислений.
- Не рисовать фиктивные online/progress/results. Не выдавать mock-тесты за проверку устройства или аккаунта.
- Не копировать Vela/WoozyLLM без ясной лицензии; не включать сторонние шрифты.
- Нет raw-RPC, unsandboxed shell, accept-for-session, auto-approve, TLS bypass и автоматического подключения пользовательских папок.
- Консервативный default read-only; разрешения не повышаются автоматически при несовместимости протокола.
- Схема установленного Codex важнее примеров документации. Проверять конкретные поля, а не совпадения enum во всём JSON.

## Состояние после M1 cross-build

72 Python tests (55 bridge/compatibility + 17 packaging), 35 grouped UI-model checks, 23 grouped native-input checks. Реальная ARM-кросс-сборка VPK 00.11 прошла; скачанный пакет повторно проверен. Точные коммит, CI runs, digest SDK и SHA-256 в docs/M1_BUILD_RESULTS.md. Это НЕ аппаратная проверка и НЕ работа с аккаунтом владельца. Native HTTPS и штатная диктовка ещё не написаны.

## Следующее

1. Проверять CI конкретного HEAD; прежний успешный прогон не доказывает последующие коммиты.
2. Hardware smoke-test по docs/HARDWARE_TEST.md; не закрывать #2 по одной компиляции. Не ставить firmware/plugins и не перезаписывать чужой Title ID.
3. Реальный Codex на Windows: doctor, ChatGPT-login, read-only scratch thread, проверка эффективных разрешений (#3).
4. Асинхронный native HTTPS с лимитами JSON, проверкой сертификата, сопряжением и восстановлением после разрыва без повторного исполнения (#4).
5. Штатная диктовка как отдельный gate (#5), без платной запасной реализации.
6. Перед стабильным публичным релизом закончить аудит лицензий статически включаемых библиотек/нотисов и аппаратную матрицу. Текущий artifact — тестовый, не stable release.

## Проверки

```sh
python -m unittest discover -s tests -v
g++ -std=c++17 -Wall -Wextra -Werror -pedantic tests/ui_model_test.cpp -o ui_model_test
./ui_model_test
g++ -std=c++17 -Wall -Wextra -Werror -pedantic -Itests/fixtures/vita_sdk tests/native_input_test.cpp client/src/microphone.cpp -o native_input_test
./native_input_test
```

Vita build: `.github/workflows/vita-build.yml` и docs/BUILD.md. SDK doubles используются только в host-тесте, никогда в include path настоящего клиента. Проверка VPK: `python scripts/verify_vpk.py build/vita/codex-vita-ui-prototype.vpk`.

Обновлять docs/STATUS.md после этапа. Не менять отчёты на «успех», пока соответствующие проверки не выполнены. Старые docs/TEST_RESULTS.md и docs/test-run.txt относятся к bootstrap-этапу; M1 имеет отдельный датированный отчёт.
