# Codex Vita

Неофициальный нативный пульт PS Vita для Codex на компьютере. Репозиторий `Merkos-free/Vita-codex` создан владельцем публичным; видимость не менялась.

**00.20 — подключаемый тестовый кандидат, не стабильный релиз.** Реальная ARM/VPK-сборка получена. Общий C++ клиент прошёл сквозной HTTPS-тест с настоящим bridge и явно обозначенным подставным Codex. Официальный Codex 0.155.1 отдельно проверен на Windows/Linux без аккаунта и без модельных заданий. Работа на физической Vita и с аккаунтом владельца пока не подтверждена.

## Что реализовано

Нативные страницы: проекты и диалоги, чат с обеими ролями, черновик, действия/статусы, прокручиваемый diff, одноразовые подтверждения, голосовой индикатор и настройки. Реальные данные берутся из bridge; тестовые сообщения включаются только в отдельном desktop capture-режиме с явной маркировкой.

HTTPS реализован через общий libcurl multi-клиент. Обязательны CA и проверка IP, только `https://IPv4:port`, без DNS, прокси, редиректов и отключения TLS. Токен устройства хранится в RAM. Новые задания не повторяются после сетевой ошибки: используется журнал requestId и запрос состояния. Остановка не ждёт общей очереди операций bridge.

**Голосовое распознавание НЕ реализовано.** Требование владельца — штатная диктовка Codex через ChatGPT, без отдельного платного STT. Никакой подмены API, Whisper или другим сервисом. Вкладка «Голос» — только локальный индикатор микрофона Vita.

## Структура

- `client/shared/`: общие JSON, HTTPS, Session и UI-компоненты для Vita и компьютера.
- `client/src/`: VitaSDK/libvita2d, кнопки/touch, системная клавиатура, локальный микрофон.
- `client/host/`: headless интеграционный драйвер и SDL2 desktop renderer. Это НЕ эмулятор Vita.
- `bridge/codex_vita/`: узкий адаптер официального app-server, сессии, история, одноразовые approvals, журнал запросов и локальный HTTPS.
- `tests/`: модульные проверки и реальный HTTPS-стенд с явно обозначенным JSONL test double.
- `scripts/`: инспектор VPK, pinned curl build и проверка официального Codex без аккаунта.

## Подготовка Windows — позднее, когда потребуется реальное подключение

Нужны Python 3.11+, официальный Codex с самостоятельным ChatGPT-login и локальный OpenSSL для создания сертификата. Пример ниже не запускается автоматически: укажите собственный LAN IPv4 и отдельную тестовую папку. Не вводите пароли или OpenAI API-ключи в Vita.

```powershell
$env:PYTHONPATH = Join-Path $PWD 'bridge'
python -m codex_vita.setup --host 192.168.1.10 --project C:\Projects\vita-scratch --output .local/setup
python run_bridge.py --config .local/setup/config.json
```

`setup` сначала проверяет схему установленного Codex и выбирает только read-only/on-request. Он не вызывает модель, не входит в аккаунт, не открывает порт и не изменяет firewall. Конфигурация и сертификат создаются в НОВОМ каталоге; существующий не перезаписывается. Сертификат действует 30 дней, содержит выбранный IP. При смене IP/истечении подготовить новый каталог и явно заменить доверенный сертификат на клиенте.

На Vita позже переносится **только содержимое `.local/setup/vita/`** в `ux0:data/vita-codex/`. Там публичный `ca.pem`, адрес `connection.json` и SHA-256 сертификата. **`server-key.pem` остаётся на ПК; никогда не копировать его на Vita или в Git.** Выбирать личный каталог с закрытыми правами; на Windows также проверить унаследованные ACL.

Bridge при запуске проверяет ChatGPT-login и выводит одноразовый PIN. Сопоставьте адрес и сертификат, затем введите PIN в настройках клиента. Доступ только в своей сети; не пробрасывать порт и не публиковать сервис в интернет. Первые реальные задачи — исключительно в scratch-папке. Allowlist cwd не доказывает изоляцию чтения/MCP, а проверка схемы не доказывает эффективную sandbox-политику.

## Проверки без устройства и аккаунта

```sh
python -m unittest discover -s tests -v
g++ -std=c++17 -Wall -Wextra -Werror -pedantic tests/ui_model_test.cpp -o ui_model_test
./ui_model_test
g++ -std=c++17 -Wall -Wextra -Werror -pedantic -Itests/fixtures/vita_sdk tests/native_input_test.cpp client/src/microphone.cpp -o native_input_test
./native_input_test
```

Сетевая/desktop-сборка на Linux с dev-пакетами libcurl, SDL2, SDL2_ttf:

```sh
mkdir -p build/host
g++ -std=c++17 -Wall -Wextra -Werror -pedantic client/host/probe.cpp client/shared/https.cpp $(pkg-config --cflags --libs libcurl) -o build/host/probe
CV_NATIVE_PROBE="$PWD/build/host/probe" python tests/native_e2e.py -v
g++ -std=c++17 -Wall -Wextra -Werror -pedantic client/host/desktop.cpp client/shared/https.cpp $(pkg-config --cflags --libs sdl2 SDL2_ttf libcurl) -o build/host/codex-vita-desktop
build/host/codex-vita-desktop --font /path/to/installed/font.ttf --endpoint https://127.0.0.1:8765 --ca /path/to/public-ca.pem
```

Шрифт предоставляется локально и не распространяется. `--capture build/screens` создаёт шесть ЯВНО ТЕСТОВЫХ BMP со значениями fixture; они не являются скриншотами Vita. Стандартные desktop-кнопки: F1–F6 вкладки, Tab фокус, Enter действие, стрелки/колесо прокрутка, Esc назад. Подтверждение — удержание Enter после просмотра деталей.

## Сборка Vita

См. `docs/BUILD.md`, `.github/workflows/vita-build.yml`. SDK image закреплён по digest; curl 8.17.0 скачивается по точному SHA-256 и пересобирается для устранения ABI-несовместимости внутри SDK. Сама компиляция идёт без сети и credentials. Используется upstream-ограничение консольных engine/provider hooks; проверка сертификатов не выключается.

Идентификатор тестового пакета `CVITA0001`; версия `00.20`; имя `Codex Vita Test`. Не перезаписывать другое приложение с таким ID. Успех упаковки не является аппаратным тестом. Установка сейчас не обязательна для продолжения разработки.

## Открытые этапы

Физическая Vita (Wi-Fi/TLS, IME, микрофон, power/suspend, производительность), настоящий аккаунт и sandbox, полноценный Windows GUI/EXE, полировка/просмотр diff по файлам, штатная диктовка, аудит зависимостей и лицензий перед стабильным распространением. Не подключать чувствительные production-проекты. Подробнее: `AGENTS.md`, `docs/STATUS.md`, `docs/ROADMAP.md`, `SECURITY.md`.

Не связан с OpenAI или Sony. Оригинальный код пока без выбранной владельцем лицензии. Сторонние шрифты, Vela/WoozyLLM и бинарник Codex не включены.
