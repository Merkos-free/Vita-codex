# Проверки 00.21 / PR #9

Дата 2026-10-03. Проверенный код: `06ff59da79ab0042ab8bc88135de403203ab6e32`. Полное дерево `bf39373b48d0a945381ac4ab89243c5f09e48eb3` совпало с локальными исходниками. GitHub PR checkout: `79f2470d4ce5fed7e97a81f909a27439af74ebf3`.

## Успешный CI этого кода

- source-tests: https://github.com/Merkos-free/Vita-codex/actions/runs/37101496077
- connected-client: https://github.com/Merkos-free/Vita-codex/actions/runs/37101496130
- vita-build: https://github.com/Merkos-free/Vita-codex/actions/runs/37101496076
- windows-companion: https://github.com/Merkos-free/Vita-codex/actions/runs/37101496120

121 Python tests, 49 network-model checks, 35 legacy UI-model и 23 native-input (SDK doubles). Новые: 188 diff/parser/UI checks, 250 deterministic malformed samples под ASan/UBSan, восемь контрактов с настоящим Git в отдельной temp-папке. Полная HTTPS-серия — 11 тестов с настоящим общим C++ клиентом/bridge и ЯВНЫМ подставным Codex; не модель и не пользовательский аккаунт.

Локальная первая E2E-попытка была остановлена timeout. Повторная полная серия прошла 11 тестов за 53.357s. Никаких проверок не отключалось. Официальный Codex 0.155.1 дополнительно проверен в CI без аккаунта (схема/инициализация), не model execution.

## Проверенные загрузки

VPK artifact 11266965899, 1841575 байт VPK, Title ID CVITA0001, версия 00.21. Внешний ZIP SHA-256 `632f038f1751202a3440f874ba694573647bceae44168bd837ffe04fa8c457dc` совпал с GitHub digest. VPK повторно проверена scripts/verify_vpk.py; её SHA-256 `6e38dc3cc97607ab208a3a5732111c69f8a83239e5fcbd18a2ff74513fea4df6`.

Windows artifact 11265877431: ZIP 12988774 байт, SHA-256 `4433ba8761498f3adef1e8302c6c1cdd8b6297fb947b9c54684d34624420dddf`. Проверены 996 файлов manifest, PE x64, отсутствие файлов шрифтов, private PEM и аудио. Настоящее GUI было открыто/закрыто CI в idle; ноутбук владельца не использовался. Это тот же Companion, не новая голосовая реализация.

Desktop artifact 11266406842: ZIP SHA-256 `56bdf87cf200f9c249320981325530d16b518d5a11022634392613432c389c50`. Восемь BMP 960x544; список файлов, отдельный diff, поиск и approvals осмотрены визуально. PNG получены преобразованием этих BMP, а не генерацией ИИ. Явная маркировка TEST FIXTURE / NO CODEX / NO VITA сохраняется.

Время хранения CI-артефактов ограничено. Последующая документационная доработка требует своего CI перед merge; результат фиксируется в PR #9. Hardware/account/voice не проверены; stable release и лицензионная приёмка не объявляются.
