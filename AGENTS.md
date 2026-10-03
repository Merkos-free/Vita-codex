# Codex Vita: инструкции разработчику

Работать только в `Merkos-free/Vita-codex`. Прочитать README, docs/STATUS.md, docs/ROADMAP.md, docs/VOICE.md, docs/WINDOWS_COMPANION.md и SECURITY.md. Репозиторий публичный по решению владельца; видимость не менять. Ветки и PR, без force-push, чужих проектов, секретов, auth.json, аудио, private keys или личных настроек в Git.

## Непересматриваемые требования

- Нативный UI Vita. Не заменять браузером/удалённым рабочим столом/терминалом без нового решения владельца.
- Официальный Codex на компьютере с ChatGPT-login. Credentials не передаются на Vita и не используются для самодельных вызовов внутренних endpoints.
- Голос — встроенная диктовка самого Codex. Нет платного STT API, Whisper, локальной модели или подмены провайдера. Audio/realtime в схеме не доказывает Dictate или условия тарифа. Пока voiceValidated=false.
- Никаких фиктивных online/results в обычном приложении. Fixtures только в тестах и маркированном capture-режиме. Не выдавать компиляцию/host-tests за аппаратный или аккаунтный тест.
- Не копировать Vela/WoozyLLM без ясной лицензии; не включать сторонние файлы шрифтов.
- Нет raw-RPC, unsandboxed shell, accept-for-session, auto-approve, TLS bypass и автоматического подключения личных папок.
- Default read-only; права не повышаются при несовместимости. GUI Companion принимает только read-only/on-request и явную тестовую папку. Проектная allowlist не доказывает фактическую sandbox-изоляцию чтения/MCP.
- Проверять конкретные поля схемы установленного Codex, не совпадения enum по всему JSON.
- Не выставлять Bridge в интернет, не менять firewall/NAT автоматически, не создавать платные ресурсы.

## Автономность

Владелец явно отложил промежуточную аппаратную проверку. Продолжать UI/сеть/Windows/CI без требования фото Vita. Hardware/account gates #2/#3/#4 не закрывать без фактического результата. Штатная диктовка #5 остаётся отдельной проверкой возможности.

## Текущая реализация

Общий C++ Session/HTTPS/Ui и SDL desktop renderer; VPK 00.20. Bridge protocol v2 с обязательным requestId мутаций. Журнал только RAM, не exactly-once после перезапуска. Не повторять неизвестную операцию; токены отзываются после остановки. Snapshot revision fencing не позволяет старому idle-снимку разрешить отправку после нового задания.

Windows Companion: `run_companion.py`, `companion.py` и `gui.py`; одно рабочее выполнение, thread-safe immutable status, Tk обновляется только на главном потоке. Остановка отзывает токены, но не обещает rollback или убийство всех фоновых процессов. ZIP для Vita содержит только CA, endpoint, fingerprint. GUI-окно не запускает сервер/логин/модель автоматически.

## Проверки

- `python -m unittest discover -s tests -v` — 121 тест на этапе companion.
- C++ ui_model_test: 35 grouped checks; native_input_test: 23 checks с SDK doubles, не устройство.
- network-tests.yml: общий C++ клиент, HTTPS E2E через native_ordering_e2e.py, официальный Codex 0.155.1 без аккаунта и шесть маркированных desktop BMP.
- windows-companion.yml: real Tk contract-test, Windows portable build и запуск готовой EXE в idle. Codex/Node/OpenSSL не поставляются в этом пакете. Файлы шрифтов запрещены проверкой пакета.
- vita-build.yml: hash-pinned curl/SDK, компиляция без сети/credentials, VPK validator. SDK doubles не попадают в настоящий include path.

Перед merge проверить CI конкретного HEAD. Обновлять STATUS/PR реальными результатами, не переписывать исторические отчёты как текущие. Полный лицензионный аудит перед stable остаётся открытым.

Следующие автономные задачи: per-file diff/поиск, UI-state/layout тесты, улучшение диагностики, исследование штатной Dictate-функции. Не пересоздавать существующие компоненты и не раздувать количество UI-фреймворков без необходимости.
