# Changelog

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
