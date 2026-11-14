# Changelog

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
