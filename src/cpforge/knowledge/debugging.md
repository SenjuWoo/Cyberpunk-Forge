# Debugging a broken mod setup

1. `cpforge logs` - one report over:
   - `r6/logs/redscript_rCURRENT.log` (compile errors grouped by mod, warnings counted per mod)
   - `red4ext/logs/*` (loader and plugin logs)
   - ArchiveXL / TweakXL / Codeware logs in their plugin folders
   - CET `cyber_engine_tweaks.log`, `scripting.log` and per-mod logs
   - Input Loader and Mod Settings logs
   - recent crash reports in `%LOCALAPPDATA%\REDEngine\ReporterQueue`
   Each source is matched against the known-error registry
   (`cpforge explain "<line>"` for a single message).
2. Read which file an error points at before blaming a mod: the redscript
   failure summary lists every mod whose file failed, and a library mod
   (Codeware, Mod Settings) erroring usually means a mod that depends on it is
   outdated, or the library itself is behind the game patch.
3. `cpforge conflicts` for mods fighting over the same method, resource or record.
4. After a game patch, update the frameworks first (RED4ext, redscript, CET,
   ArchiveXL, TweakXL, Codeware), then mods. `cpforge game` shows installed
   framework versions next to the game version.
5. Bisect: disable half the suspects, relaunch, repeat. One change per launch.

A clean compile is not a runtime result. Report compile, load and gameplay
separately.
