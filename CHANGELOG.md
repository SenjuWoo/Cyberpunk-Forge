# Changelog

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
