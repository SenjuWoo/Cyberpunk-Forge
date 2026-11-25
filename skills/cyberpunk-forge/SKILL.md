---
name: cyberpunk-forge
description: Make, check, fix, package and publish Cyberpunk 2077 mods with Cyberpunk Forge (cpforge). Use for redscript, Cyber Engine Tweaks Lua, TweakXL, ArchiveXL, RED4ext C++ plugins, Input Loader, Mod Settings, Audioware, REDmod, WolvenKit archives, mod conflicts, broken mods after a game patch, redscript compile errors, CET errors, and Nexus releases.
---

# Cyberpunk Forge (cpforge 0.6.2)

Use the forge as the evidence layer. Never write a class, method, record or
resource path from memory when `cpforge` can read it from the installed game.

If `cpforge` is not on PATH, run `cpforge.cmd` from the forge folder or
`<forge>\.venv\Scripts\cpforge.exe`. Every command prints JSON; exit 0 ok,
1 findings, 2 named failure (read `fix`), 3 bug.

## Default sequence

1. `cpforge doctor` - game found, version (2.5 = file version 3.0.88.46235),
   frameworks and their versions, tools, whether an index exists.
2. `cpforge index` if the doctor says the index is missing (once per patch).
3. `cpforge plan "<the request>"` - route, templates, docs, steps, what to avoid.
   Read the docs it names: `cpforge knowledge <name>`.
4. New mod: `cpforge new "<Name>" --kind <kind> [--kind ...]`. Existing mod:
   work in its project (folder with `cpforge.json`), or create one around it.
5. Look up before writing:
   - `cpforge api class <Class> [--filter <text>]`, `cpforge api search <text> --kind func`
   - `cpforge tweak search <words>`, `cpforge tweak show <Record>`
   - `cpforge archive find <resource path> --vanilla`
   - `cpforge res inspect <file.mesh|.app|.ent>` - components, lights, slots,
     materials of a game resource; `cpforge res check` before every WolvenKit
     deserialize; `cpforge res roundtrip` to prove a file survives JSON editing
6. `cpforge check --compile` - fix every error; read `gaps` and say which
   checks did not run. `RS-NATIVE-VIA-MOD` means a call compiles only because
   another installed mod declares it: add that mod to `script_dependencies` or
   use FTLog-style vanilla calls.
7. Runtime: `cpforge deploy`, the user tests in game, `cpforge logs --mod <Id>`,
   `cpforge undeploy`. Only the user's game session is runtime evidence.
8. Release: `cpforge bump <part>`, write CHANGELOG.md, `cpforge package`,
   `cpforge nexus`. The forge never uploads.

## Surface choice (least powerful first)

TweakXL data < redscript (prefer `@wrapMethod`) < CET Lua < ArchiveXL resources
< RED4ext native. New cars and bikes: `cpforge knowledge vehicles` first (copy a
vanilla car of the same layout; rigs, frames, light zones, WolvenKit import). Mod Settings for options, Input Loader for key bindings,
Audioware for sound, REDmod only when a REDmod package is required.

## Broken setup or broken mod

`cpforge logs` (all logs, matched against known errors), `cpforge conflicts`,
`cpforge explain "<error line>"`. After a game patch: update frameworks first,
`cpforge index` (the old patch's index is kept), `cpforge api diff <old> <new>
--project <mod>` to list hooks that hit removed API, then
`cpforge check --compile` on each mod you own.

## Rules

- The game folder and mod-manager staging are read-only except through
  `cpforge deploy` (receipt + backups; `undeploy` reverses it). Warn the user
  when Vortex manages the game folder. Deploy refuses to overwrite a file it
  did not write, or one edited in the game folder since, unless `--force`
  (which backs it up); a failed deploy still leaves a receipt for `undeploy`.
- Report evidence tiers separately: static check, compile, package, in-game
  load, gameplay. A clean compile is not a runtime result.
- Facts with provenance: `cpforge facts <key>`. If a fact is marked `docs` or
  `observed` and matters, verify it against the install before relying on it.
- Never put API keys in mod files; `cpforge validate` scans for them.
