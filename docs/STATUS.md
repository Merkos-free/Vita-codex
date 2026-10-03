# Статус: кандидат 00.21 / просмотр diff по файлам

Проект `Merkos-free/Vita-codex`, public. Промежуточная аппаратная проверка отложена владельцем и не блокирует разработку. Она НЕ объявлена пройденной.

## Сохранённая основа 00.20

PR #7 объединён в `main` (`91501159e2278eac5a9b150622720ed880b263a5`). Уже реализованы общий C++ Session/HTTPS/UI для Vita/SDL, bridge v2 с requestId/revision fencing, история обеих ролей, interrupt, одноразовые approvals и Windows Companion с portable EXE. Итоговые успешные runs PR #7: source-tests 37092067868, connected-client 37092067872, vita-build 37092067912, windows-companion 37092067924. Их успех не переносится автоматически на новые коммиты.

## Новое в 00.21

Ветка `feat/diff-review`. Read-only diff index, список/выбор файлов, полноэкранный просмотр, точный поиск и переход по совпадениям. Git/unified headers, UTF-8 octal paths, rename/delete/binary, явные лимиты и предупреждение о частичном diff. Пути только отображаются, не открываются; нет Apply.

Единое управление Vita/SDL, отсечение устаревших кнопок по epoch/page и approval ticket/details, сброс удержания при смене фокуса. Подписи укладываются в экран по реальным метрикам шрифта. Восемь маркированных desktop captures. Детали: `docs/DIFF_REVIEW.md`.

## Проверки этого этапа

Локально Linux: 121 Python tests; 49 network-model checks; 188 diff/parser/UI checks + 250 malformed samples под ASan/UBSan; восемь контрактных сценариев с настоящим Git в временном репозитории. Полная локальная HTTPS-серия остановлена timeout на ordering-тесте; НЕ засчитана как успех.

CI конкретного нового HEAD (source-tests, connected-client, vita-build и windows-companion) ещё требуется проверить перед merge. SDL/VitaSDK отсутствуют в локальном контейнере; реальный рендер и ARM-сборку выполняет CI. Результаты/артефакты фиксируются отдельно в PR.

## Ограничения остаются

Физическая Vita, аппаратный Wi-Fi/IME/mic/sleep, аккаунт владельца, модельный turn и эффективная sandbox/MCP-изоляция не проверены. Dictate не реализован и не подменён платным STT. Настройка сети пока IPv4:port без DNS/интернет-туннелей. Windows GUI требует внешний Codex/Node/OpenSSL и допускает только read-only. Бинарники unsigned test candidates. Лицензия оригинального кода и аудит точных зависимостей перед stable остаются открытыми.

Следующая автономная работа: UI/layout/diagnostics и исследование поддерживаемой штатной диктовки. Не требовать фото Vita для продолжения. Не закрывать #2/#3/#4/#5 по одним CI-тестам.
