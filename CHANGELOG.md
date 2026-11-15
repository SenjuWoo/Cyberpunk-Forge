# Changelog

## 0.6.0 - 2026-11-15

Audit release: safety and correctness fixes, no new commands.

- `deploy` no longer writes through hard links. Vortex deploys by hard link, so
  `deploy --force` over a Vortex-managed file used to change the copy in the
  mod manager's staging folder too, and `undeploy` did not repair it. Files are
  now replaced by rename.
- `deploy` refuses to overwrite a file it deployed earlier that was edited in
  the game folder since (`--force` saves the edited copy first). A deploy that
  stops halfway (a locked file, a file where a folder must go) now writes a
  receipt for what it wrote, so `undeploy` can take it back out.
- `undeploy` keeps the receipt when the game folder is not reachable (it used
  to delete it and remove nothing), and names the backup of any file it left in
  place because it changed after deploy.
- `compile` and `check --compile` compile all of `game/r6/scripts`: loose
  `.reds` files were skipped, and two files with the same name in different
  folders overwrote each other in the scratch copy. Compiler errors point at the
  exact project file.
- A compile timeout stops only its own compiler; it used to end every
  `scc.exe` on the machine, including the game's own startup compile.
  `compile --keep` no longer clears a `scripts` folder the forge did not create.
- Ordinary bad input is now a finding or a named failure instead of an internal
  error (exit 3): malformed `info.json`, `.archive.xl` or Audioware manifest, a
  damaged archive next to an `.archive.xl`, a damaged index, a truncated
  `tweakdb.bin` or `.str`, `res check` with no game found, `new` with `:` or
  `?` in the name, and tools that cannot be started or do not finish.
- `cpforge game`/`doctor` counted loose files as redscript mods, and with `[`
  in the game path counted nothing; `logs` found no logs in such a folder.
- Templates escape quotes and backslashes in the mod name, description and
  author, so `info.json`, Lua and redscript stay valid.
- `new --force` into an existing project names the new files after the
  project's id, not the name given on the command line, and does not repeat
  version mirrors.
- A version mirror whose file is gone or whose pattern no longer matches is
  reported by `check` (`VERSION-FILE-MISSING`, `VERSION-PATTERN`) and listed
  under `skipped` by `bump`, instead of being passed over silently.
- The `source/` secret scan no longer skips everything when the project lives
  under a folder named `build`; an Anthropic key is reported once, not twice.
- A tool variable (`CPFORGE_LUA`, `WOLVENKIT_CLI`) pointing at a missing file no
  longer hides the same tool on PATH. `conflicts` without an index still
  reports archive and tweak conflicts.
- `validate` reads only text members for the secret scan, instead of inflating
  every `.archive` into memory (a 300 MB archive used 600 MB).
- Packaging: SPDX license expression in `pyproject.toml` (the table form stops
  working in setuptools in 2027). CI also runs Python 3.14.

## 0.5.1 - 2026-11-15

- `knowledge vehicles`: doors are confirmed animating in game on a car's own
  animset copy, and the wheel fix is confirmed by the in-game slot probe
  (wheel slots match the rig). Hood, trunk and window animation on an own
  animset is marked not verified.

## 0.5.0 - 2026-11-15

- `cpforge res check` on an `.ent` checks the animset/rig pairing: every
  animset the entity plays must embed the rig of its `deformation_rig`
  component (the project's own `.anims` is read through WolvenKit), and must be
  listed in `resolvedDependencies`. A car that keeps the base car's `.anims`
  with its own deformation rig gets `RES-ENT-ANIMSET-RIG`: in game that draws
  the wheels at 2 x the car's suspension position minus the base car's.
  Calibrated on a real car: its current entity passes, the same entity pointed
  back at the base car's animset is flagged, and the vanilla entity passes.
- `knowledge vehicles`: the animset/rig pairing and `animations.hash`, an
  in-game slot probe for CET (out-parameters come back as return values), the
  fuel-port component to drop, results from in-game tests, and new pitfall rows.

## 0.4.0 - 2026-11-15

- `cpforge res check | inspect | roundtrip <files>` for game resources (CR2W or
  WolvenKit JSON):
  - check: repeated or dangling handle ids, repeated compiledData BufferIds,
    numeric empty ResourcePaths, CruidDict vs chunk ids, `components` vs chunks,
    mesh submesh count vs each appearance's chunkMaterials, material entries vs
    instances, lights without type or zone, proxy without proxy component, and
    every referenced resource looked up in the project's `source/archive` and the
    game's archives (bare hashes are named from the project tree).
  - inspect adds components, meshes, lights (type, zone, binding), slots and
    proxy per appearance; roundtrip proves CR2W -> JSON -> CR2W gives the same
    bytes.
  - Calibrated on a real car build and the vanilla Archer Hella: 79 files clean,
    0 unresolved references; a copied appearance with repeated handles is
    flagged with the same cause WolvenKit fails on.
- `check` warns about resource paths in tweaks that exist in neither the project
  nor any game archive (`TWEAK-RESOURCE`), and about a car based on a
  `_player` record that is not appended to `Vehicle.vehicle_list`
  (`VEHICLE-NOT-LISTED`).
- Fixed: YAML flats and references on records that live only in the vanilla
  `.tweak` sources (e.g. `Vehicle.vehicle_list`) were reported as missing;
  `cpforge tweak exists` now finds them too and says where.
- Fixed: a corrupt CR2W (WolvenKit leaves an empty .json) and a binary `.json`
  game resource are reported per file instead of stopping the command.
- `knowledge vehicles` covers the whole car build: extraction, frame and mesh
  conventions, rigs and steering, glb import rules, materials, lights, `.app`/
  `.ent` compiledData, `.phys`, TweakXL/dealer/localization/inkatlas, and a
  pitfall table, from a complete car project.

## 0.3.0 - 2026-11-14

- Vehicles: `cpforge plan` routes car, bike and vehicle requests to a new
  `vehicle` route, and `cpforge knowledge vehicles` documents the conventions
  read from vanilla 2.5 cars and WolvenKit 9.1 round trips in a real vehicle
  project: reference rigs and additive door/hood/trunk clips, base rigs by
  wheelbase and track, the model frame, bone-local unskinned part meshes,
  submesh naming, light zones in vertex colour and the `lightType` bits, mesh
  import onto vanilla templates, the WolvenKit tangent sign, and the material
  JSON layout.
- WolvenKit CLI is found without `WOLVENKIT_CLI` when it sits in the dotnet
  tools folder or the Reverse THIS! kit folder; `cpforge doctor` shows the path.
- Release notes say how to rebuild the source zip byte for byte (`TZ=UTC git
  archive`; zip timestamps are local time).

## 0.2.0 - 2026-11-14

- `.tweak` files (RED TweakDB syntax) are checked: records, attributes, typed
  fields, inline records with a base, top-level flats, and the line of the
  first missing `;` or `,`, unclosed string or bracket. Bases and record
  references are checked against TweakDB, the vanilla sources and installed
  tweaks. The parser reads every vanilla `.tweak` file of a 2.5 install and 71
  installed mod files without a finding.
- Calls to engine natives that vanilla never declares (the `LogChannel` trap)
  are flagged before compiling: `RS-NATIVE-ONLY` when nothing declares the
  function, `RS-NATIVE-VIA-MOD` when it compiles only because another installed
  mod declares it. Mods listed in `script_dependencies` or `requires` count.
- `cpforge api versions` lists stored indexes; `cpforge api diff <old> <new>`
  reports removed and added classes, methods, fields, globals, enum values and
  TweakDB records and changed signatures between two game patches, and with
  `--project` the project's hooks that point at removed API.
- The index now includes base-less `.tweak` records (`baseState { }`) and
  dotted record names; on 2.5 that is 76.3k records instead of 75.3k. Index
  schema 3: run `cpforge index` once.
- CI runs the installer twice, then the uninstaller, on Windows. A tag `vX.Y.Z`
  publishes the release from a commit with a green CI run: the tag must match
  the version and the CHANGELOG, the source zip is built twice and compared,
  and its SHA-256 is attached.

## 0.1.0 - 2026-11-14

First release.

- `cpforge` CLI with JSON output and stable exit codes: doctor, capabilities,
  plan, knowledge, facts, game, index, api, tweak, hash, archive, conflicts,
  logs, explain, templates, new, check, compile, build, package, validate,
  deploy, undeploy, bump, nexus.
- Local index of the installed game: vanilla script source and native RTTI
  from the REDmod DLC, installed mods' `.reds`, vanilla TweakDB source.
- Readers for `.archive` (RDAR index, FNV-1a 64 path hashes), `tweakdb.bin`
  (record IDs and type keys) and REDmod `tweakdb*.str` name tables, each
  checked against a 2.5 install.
- Project checks: hook targets, record types and references, ArchiveXL paths
  inside the built archive, CET events, Input Loader XML, REDmod and Audioware
  manifests, version mirrors, leaked API keys; optional redscript compile with
  the game's `scc.exe` on a scratch copy.
- Nine templates: redscript, modsettings, cet, tweakxl, archivexl, input,
  red4ext, audioware, redmod.
- Deterministic packaging with receipts, zip validation, deploy/undeploy with
  backups, version bump with last-known-good copy, Nexus page kit.
- Agent skill, installer and uninstaller.
