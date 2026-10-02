# Сборка офлайн-клиента Vita

Рабочий проверенный вариант — `.github/workflows/vita-build.yml`. Он запускает host-тесты, кросс-компиляцию, валидатор VPK и сохраняет test bundle/evidence. В контейнер не передаются credentials, сеть для компиляции отключена. Никакого model/API трафика.

## Повторить локально с Docker (Linux)

```sh
SDK_IMAGE='vitasdk/vitasdk@sha256:7f5eee50ff95b73c8c847dbfef6227aa0035886444b4d0254c21da8369ff1efc'
docker pull "$SDK_IMAGE"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" -w /workspace "$SDK_IMAGE" \
  sh -ec 'cmake -S client -B build/vita -DCMAKE_BUILD_TYPE=Release; cmake --build build/vita --parallel 2'
python3 scripts/verify_vpk.py build/vita/codex-vita-ui-prototype.vpk --report build/evidence/vpk-report.json
```

Команды Docker нужны разработчику, а не владельцу Vita для установки уже собранного пакета. Нативная сборка на Windows без контейнера отдельно не проверена.

## При установленном VitaSDK

```sh
# VITASDK должен указывать на проверенную установку SDK.
cmake -S client -B build/vita -DCMAKE_BUILD_TYPE=Release
cmake --build build/vita --parallel 2
```

Нужны libvita2d, png/jpeg/zlib, SDK stubs и host Python3. Скрипт генерирует оригинальные palette PNG и LiveArea XML во временной папке build/vita/assets. CMake включает SceAppMgr_stub для актуальной libvita2d. В release сборке C++ warnings рассматриваются как ошибки; -fpermissive не применяется.

## Уровни проверки

Host-тесты проверяют логику и форматы. ARM-компиляция проверяет совместимость с SDK и линковку. `verify_vpk.py` проверяет состав/структуру пакета и вычисляет хэш, но не симулирует Sony OS. Наконец, отдельный hardware smoke-test проверяет реальное устройство; см. HARDWARE_TEST.md.

GitHub artifacts хранятся 14 дней. При pull_request checkout является тестовым merge commit; точный SHA включён в source-commit.txt. Пинning SDK не доказывает битовую идентичность всех повторных сборок — сравнивайте SHA256SUMS для конкретного артефакта.
