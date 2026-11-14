# Cyberpunk Forge

A local toolkit for making, checking, fixing and shipping **Cyberpunk 2077**
mods: redscript, Cyber Engine Tweaks (Lua), TweakXL, ArchiveXL, RED4ext (C++),
Input Loader, Mod Settings, Audioware and REDmod.

It reads facts from **your installed game**, not from memory. Before you hook a
method or reference a record, the forge has already checked that it exists in
your patch.

- `cpforge` CLI: every command prints JSON and returns a stable exit code, so it
  works for people and for AI coding agents.
- An agent skill (`skills/cyberpunk-forge/SKILL.md`) that tells an agent how to
  use it.
- Offline, local-first. It never downloads mods, never uploads, and never
  writes to your game folder unless you run `cpforge deploy`.

## What it does

| Need | Command |
|---|---|
| Is my setup healthy? Game version, frameworks, tools | `cpforge doctor` |
| Which approach fits my idea? | `cpforge plan "add a new jacket to a vendor"` |
| Start a mod from a template | `cpforge new "My Mod" --kind redscript --kind modsettings` |
| Look up real classes, methods, fields, enums | `cpforge api search OnAction`, `cpforge api class PlayerPuppet` |
| Look up TweakDB records and their vanilla source | `cpforge tweak search lexington`, `cpforge tweak show Items.Preset_Lexington_Default` |
| Validate a project against the installed game (hooks, records, `.yaml` and `.tweak` tweaks, native-only calls) | `cpforge check --compile` |
| What did a game patch remove or change? Which of my hooks break? | `cpforge api versions`, `cpforge api diff 2.31 2.5 --project .` |
| Compile redscript with the game's own compiler (scratch copy) | `cpforge compile` |
| Build a RED4ext plugin (CMake) or pack an archive (WolvenKit CLI) | `cpforge build` |
| Release zip (deterministic, validated, with receipt) | `cpforge package` |
| Check any mod zip for layout mistakes and leaked API keys | `cpforge validate mod.zip` |
| Install into the game for testing, and take it back out | `cpforge deploy`, `cpforge undeploy` |
| Read all mod logs at once (redscript, RED4ext, CET, ArchiveXL, TweakXL, Codeware, crashes) | `cpforge logs` |
| Find mods fighting over methods, resources or records | `cpforge conflicts` |
| Bump the version everywhere, keep the last good zip | `cpforge bump minor` |
| Nexus page kit (BBCode, changelog, file description) | `cpforge nexus` |
| Archive and TweakDB hashes | `cpforge hash <path>`, `cpforge hash --tweakdb <Record>` |
| Which archive contains a resource? | `cpforge archive find base\...\x.mesh --vanilla` |

`cpforge capabilities` lists every command and option of the installed version.

## Templates

| Kind | What you get |
|---|---|
| `redscript` | module + a `@wrapMethod` hook on `PlayerPuppet.OnGameAttached` |
| `modsettings` | a Mod Settings menu on a `ScriptableSystem` (toggle + slider) |
| `cet` | CET `init.lua` with an ImGui window and a hotkey |
| `tweakxl` | TweakXL YAML with a cloned record |
| `archivexl` | `.archive.xl` (factory + localization) and the item record; resources go in `source/archive/` |
| `input` | Input Loader XML (context, action, rebindable key) + redscript listener |
| `red4ext` | C++20 CMake plugin on the RED4ext SDK v1 API, pinned for game 2.5 |
| `audioware` | Audioware manifest and a placeholder sound |
| `redmod` | REDmod `info.json` package |

Kinds combine: `cpforge new "My Mod" --kind redscript --kind cet --kind tweakxl`.
The redscript templates compile against the 2.5 script bundle, and CI builds
the RED4ext template on Windows.

## Install

Requirements: Windows 10/11 with the game installed, and Python 3.10+.
Optional: the free **REDmod** DLC (gives the forge the vanilla script and
TweakDB sources to index), **WolvenKit CLI** (archives), **CMake + Visual Studio
Build Tools** (RED4ext plugins), **luajit or luac** (Lua syntax checks).

```bat
START-HERE.bat
```

or `powershell -ExecutionPolicy Bypass -File Install.ps1`. It creates a `.venv`
in this folder, runs the tests, adds a `cpforge` launcher to your user PATH,
and copies the agent skill into the agent folders it finds. Nothing is
overwritten. `Uninstall.ps1` reverses it.

Without installing: `cpforge.cmd <command>` from this folder.

Then:

```bat
cpforge doctor
cpforge index
```

`index` reads your game once per patch (about 40 seconds) and stores the
result under `%LOCALAPPDATA%\CyberpunkForge`. If the game is not found, pass
`--game "<folder with bin\x64\Cyberpunk2077.exe>"` or set `CP2077_ROOT`.

## A typical loop

```bat
cpforge plan "make enemies drop more ammo"
cpforge new "More Ammo" --kind tweakxl
cd MoreAmmo
cpforge tweak search ammo loot
cpforge check
cpforge deploy        & rem test in game
cpforge logs --mod MoreAmmo
cpforge undeploy
cpforge package
cpforge nexus
```

## Project layout

```
cpforge.json   manifest: name, id, version, kinds, requirements, version files
game/          files at their game-relative paths (what ships)
source/        what builds into game/ (C++ plugin, WolvenKit resources)
CHANGELOG.md   per-version notes (feeds the Nexus kit; never packaged)
dist/          zips, checksums, receipts, Nexus kit
```

## Evidence, honestly

`cpforge check` reports what it checked, what it could not check and why
(`gaps`). A static check or a clean compile is not a runtime test; load the
game to prove behaviour. Facts the forge relies on live in
`src/cpforge/knowledge/facts.json`, each tagged with how it was established.

## Not included

No game files. The index is built on your machine from your own install and
never leaves it. Templates contain only original code.

## License

MIT. See `LICENSE` and `THIRD-PARTY.md`.
