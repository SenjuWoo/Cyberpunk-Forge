# Packaging

`cpforge package` zips `game/` exactly as it should land in the game folder:

- sorted entries, forward slashes, fixed timestamps: the same input gives the
  same bytes, so a SHA-256 identifies a release
- dev files never ship: `cpforge.json`, `STATE.md`, `PLAN.md`, logs, backups,
  `.git`, `__pycache__`, Vortex markers and backups
- writes `dist/<Id>-<version>.zip`, a `.sha256` file and a build receipt listing
  every input file and its hash
- then runs `cpforge validate` on the zip

`cpforge validate <any.zip>` works on any mod archive: backslash paths,
absolute or `..` paths, case-only duplicates, files outside the usual game
folders, loose scripts in `r6/scripts`, CET folders without `init.lua`, plugin
folders without a DLL, `.archive.xl` without its `.archive`, zero-byte files,
changelogs inside the zip, and anything that looks like an API key or token.

Install roots a mod manager expects: `r6/scripts/<Mod>/`, `r6/tweaks/<Mod>/`,
`r6/input/`, `r6/audioware/<Mod>/`, `archive/pc/mod/`,
`bin/x64/plugins/cyber_engine_tweaks/mods/<Mod>/`, `red4ext/plugins/<Mod>/`,
`mods/<Mod>/`.

Test a release by installing the zip through your mod manager, not by copying
the project folder.
