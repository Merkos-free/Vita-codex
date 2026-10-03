# Сборка подключаемого клиента 00.20

Проверенный путь — `.github/workflows/vita-build.yml`. Он выполняет host-тесты, компиляцию ARM/SELF/VPK и структурную валидацию. SDK-контейнер получает исходники без credentials; сеть при компиляции отключена. Установка SDK на компьютер владельца не требуется.

## Повторение на Linux с Docker

```sh
SDK_IMAGE='vitasdk/vitasdk@sha256:7f5eee50ff95b73c8c847dbfef6227aa0035886444b4d0254c21da8369ff1efc'
mkdir -p build/deps build/evidence
docker pull "$SDK_IMAGE"
curl --fail --location --proto '=https' --tlsv1.2 https://github.com/curl/curl/releases/download/curl-8_17_0/curl-8.17.0.tar.gz -o build/deps/curl-8.17.0.tar.gz
echo 'e8e74cdeefe5fb78b3ae6e90cd542babf788fa9480029cfcee6fd9ced42b7910  build/deps/curl-8.17.0.tar.gz' | sha256sum -c -
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace "$SDK_IMAGE" \
  sh -ec 'sh scripts/prepare_vita_curl.sh; cmake -S client -B build/vita -DCMAKE_BUILD_TYPE=Release -DCV_NETWORK_PREFIX=/workspace/build/network; cmake --build build/vita --parallel 2'
python3 scripts/verify_vpk.py build/vita/codex-vita-ui-prototype.vpk --report build/evidence/vpk-report.json
```

Нужен свободный диск для SDK и compiler build. Старый готовый libcurl в этом SDK не использовать: обнаружена ABI-несовместимость OpenSSL. curl 8.17.0 пересобирается по точному SHA-256. `OPENSSL_NO_UI_CONSOLE` применяет upstream guard отсутствующих console engine/provider hooks; сертификаты/CA/IP продолжают проверяться. В статическую группу включены pthread/stdC++.

Пакет: Title ID CVITA0001, версия 00.20, имя Codex Vita Test. Сторонние шрифты/credentials не включены. Host Python3 генерирует оригинальные palette PNG/LiveArea XML. C++ warnings-as-errors, без permissive-флагов.

## Другие уровни проверки

`.github/workflows/tests.yml`: Python Windows/Linux и C++ model. `.github/workflows/network-tests.yml`: 49 network model checks, настоящий общий C++ HTTPS -> Python bridge -> JSONL fixture, desktop SDL2 renderer и шесть явно тестовых BMP; официальный Codex 0.155.1 на Windows/Linux проверяется отдельно без аккаунта/модельных заданий. Системный шрифт Vita не эквивалентен шрифту desktop.

Ни одна из этих проверок не подтверждает запуск/сеть/ввод на устройстве или effective sandbox аккаунта. `verify_vpk.py` анализирует структуру, не эмулирует Sony OS. Аппаратный тест отложен владельцем, не отменён перед stable release.

## Артефакты

VPK/evidence хранятся в GitHub Actions 14 дней; desktop capture — 7 дней. PR checkout может быть тестовым merge commit, он указан в source-commit.txt. Пин SDK не гарантирует битовой идентичности всех сборок: сверять SHA256SUMS конкретного пакета. Исторический M1/00.11 описан отдельно в M1_BUILD_RESULTS.md.
