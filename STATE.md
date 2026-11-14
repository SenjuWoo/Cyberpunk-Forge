# STATE

Version: **0.2.0** (2026-11-14)

## Goal

A local, agent-friendly toolkit for every kind of Cyberpunk 2077 mod:
redscript, CET, TweakXL, ArchiveXL, RED4ext, Input Loader, Mod Settings,
Audioware, REDmod. Facts come from the installed game.

## Done (0.2.0)

- `.tweak` structural check + base/reference checks (parser `tweaksrc.py`,
  0 findings on 2753 vanilla and 71 installed mod files of 2.5).
- Native-only call check (`RS-NATIVE-ONLY`, `RS-NATIVE-VIA-MOD`): 0 findings on
  all installed mods' .reds; a scratch project calling `LogChannel` on the 2.5
  install gets `RS-NATIVE-VIA-MOD` naming the 4 mods that declare it.
- `cpforge api versions` / `api diff <old> <new> [--project]`.
- Index schema 3 (base-less and dotted .tweak records: 76,338 on 2.5).
- CI: installer run twice + uninstall on Windows; tag-driven release workflow.

## Done (0.1.0)

- CLI (25 commands, JSON, exit codes 0/1/2/3), skill, installer/uninstaller.
- Index of the installed game (REDmod scripts + metadata.json + installed
  .reds + vanilla .tweak sources). On a 2.5 install: 2112 script files, 2576
  .reds, 24.8k classes, 75k tweak records, 7.7k mod hooks, ~36 s.
- Readers verified against a 2.5 install: archive index (exact index-size
  match, 39/39 ArchiveXL factory hashes), tweakdb.bin (196k records; type keys
  match Murmur3 of type names), REDmod tweakdb .str names.
- Templates: redscript, modsettings, cet, tweakxl, archivexl, input, red4ext,
  audioware, redmod.

## Evidence

| Claim | Tier | How |
|---|---|---|
| Offline suite | tool-validated | `python tests/run_tests.py` (fake game tree) |
| redscript templates compile | tool-validated | `cpforge check --compile` on a 2.5 install: 0 errors (redscript + modsettings + input) |
| RED4ext template builds | tool-validated | `cpforge build` locally (MSVC 19.52, SDK commit 0f5eba4) produced the DLL; CI builds it on windows-latest |
| Templates load in game | not tested | no in-game load of any template yet |
| WolvenKit pack step | not tested | WolvenKit CLI not installed on the dev machine |
| Lua syntax check | CI only | luajit in the Ubuntu CI job; not on the dev machine |
| .tweak parser | tool-validated | every vanilla and installed .tweak file of a 2.5 install parses with 0 findings; synthetic errors located by line in tests |
| Native-only call check | tool-validated | 0 findings over installed mods; LogChannel in a scratch project flagged on 2.5 |
| api diff | tool-validated (synthetic) | offline test with two stored indexes; on the dev machine only the 2.5 index exists, so no real patch-to-patch diff yet |
| Install twice / uninstall | CI | `install` job on windows-latest |

## Next

See PLAN.md (MCP wrapper, WolvenKit unbundle/convert, Dogtown helpers,
vehicle-mod guidance from the car-mod project).

## Run / build

- Tests: `python tests/run_tests.py`
- From source: `cpforge.cmd <command>`; installed: `cpforge <command>`
- Release: bump `__version__`, CHANGELOG.md, this file; push main; CI green on
  the exact commit; push tag `vX.Y.Z`; the Release workflow publishes the zip
  and its SHA-256.
