# M1: подтверждённая кросс-сборка 00.11

Время CI: 2026-10-02, 20:52 UTC (2026-10-03, 01:52 по Уфе). Ниже результаты конкретного коммита, не обещание о будущих сборках.

## Исходники и сборка

- Branch head: `a726a3182839780713759aa8d936c59291798a1d`.
- PR #6 test merge checkout: `01e7795a3622b331a09543be728df17dc5ca9f0c`.
- Build run: https://github.com/Merkos-free/Vita-codex/actions/runs/37063251486
- Source tests run: https://github.com/Merkos-free/Vita-codex/actions/runs/37063251499
- Build job: `111024713740`, completed / success.
- Official image series: `vitasdk/vitasdk:2026.08-20260815`.
- Pinned image: `vitasdk/vitasdk@sha256:7f5eee50ff95b73c8c847dbfef6227aa0035886444b4d0254c21da8369ff1efc`.
- ARM GCC/G++ 15.2.0, CMake 3.28.3, Python 3.12.3 inside SDK image.
- ELF: ELF32, little endian, ARM, EABI5 hard-float. Converted by VitaSDK to SELF/VPK successfully.

SDK pinned by digest makes the build environment repeatable; byte-for-byte reproducibility across independent builds has NOT been established.

## Проверки

72 Python tests (55 existing + 17 package tests), Windows/Linux and Python 3.11/3.13: successful CI matrix. Windows 3.13 log explicitly reports `Ran 72 tests ... OK`. UI model: 35 grouped checks. Additional native input: 23 grouped checks compiling the production microphone code against explicit SDK doubles. Neither test type is proof of device behavior.

First ARM attempt failed on two IME UTF-16 pointer assignments. Next attempt compiled successfully but failed at link on libvita2d's shared-framebuffer/AppMgr dependencies. Both fixed without removing features or disabling warnings. The successful build keeps warnings as errors and the existing permission restrictions.

## Тестовый пакет

Package artifact: `11250604769`.
https://github.com/Merkos-free/Vita-codex/actions/runs/37063251486/artifacts/11250604769

Evidence artifact: `11250394869`.
https://github.com/Merkos-free/Vita-codex/actions/runs/37063251486/artifacts/11250394869

Artifacts have 14-day retention; source and this report remain in Git. Download of artifacts may require GitHub login. When artifacts expire, rebuild the matching commit/workflow; do not relabel unrelated binaries.

- Filename inside bundle: `codex-vita-ui-prototype.vpk`.
- Size: **143225 bytes**.
- Title ID: `CVITA0001`.
- Version: `00.11`.
- VPK SHA-256: `77c02dfb149d9bd86a7a4126181fed15b3316027d78d70ff76e0395ea9325a5d`.
- Outer artifact ZIP SHA-256: `e522c68b6f2ee530874ff4b153fdba6a1291cdd86dae58924e9b53033f42f6a5`.

Downloaded ZIP hash matched GitHub's digest. Extracted VPK was independently rechecked using `scripts/verify_vpk.py`; ID, version, size and SHA matched the build report. Evidence includes the compiler log, ARM ELF header and SDK image digest.

Package contains only `eboot.bin`, `sce_sys/param.sfo`, icon0.png and the LiveArea background/startup/template. No secrets, user settings, model files, network configuration or audio recordings. The verifier checks the exact manifest, ZIP paths/duplicates/symlinks, SFO bounds/metadata, PNG sizes/CRC, and XML assets. It does not certify runtime safety or hardware compatibility.

## Аппаратная проверка

**hardware_tested=false**. No Vita console or user Codex account was accessed during these checks. Follow `docs/HARDWARE_TEST.md`; leave issue #2 open until actual device results are recorded. Networking and built-in dictation remain disabled/unimplemented. No firmware changes or plugin installation are required by this prototype.
