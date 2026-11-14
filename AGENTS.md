# AGENTS.md - Cyberpunk Forge runbook

## Sources of truth

- Version: `src/cpforge/__init__.py` (`__version__`). Mirrors checked by tests:
  `CHANGELOG.md` top entry, `STATE.md`, `skills/cyberpunk-forge/SKILL.md`,
  `pyproject.toml` (reads the attribute).
- Domain facts: `src/cpforge/knowledge/facts.json` (each with tier + source),
  `frameworks.json` (detection markers, repos, Nexus pages), `routes.json`
  (task routing), `errors.json` (log signatures). Change data, not prose.
- Installed game beats docs: anything the forge can read from the install
  (`cpforge api`, `cpforge tweak`, `cpforge archive`) wins over memory.

## Where the logic lives

| Module | Job |
|---|---|
| `cli.py` | argparse, JSON output, exit codes, invocation log |
| `game.py` | game discovery (arg, env, Steam, GOG, Epic), versions, frameworks, inventory |
| `index.py` | API + TweakDB index from REDmod sources, metadata.json, installed .reds |
| `archive.py`, `tweakdb.py` | binary readers (RDAR, tweakdb.bin, .str), TweakXL YAML |
| `redscript.py` | scc.exe scratch compile, diagnostics parser, static hook checks |
| `check.py` | project validation, reports errors / warnings / gaps / checked |
| `project.py` | manifest, templates, bump, changelog parsing |
| `package.py` | deterministic zip, receipt, zip validation, secret scan |
| `deploy.py` | deploy/undeploy with receipt and backups |
| `build.py` | CMake (RED4ext) and WolvenKit CLI (archive) builds |
| `logs.py`, `conflicts.py`, `nexus.py`, `knowledge.py`, `doctor.py` | as named |

## Loop

1. `python tests/run_tests.py` (offline; fake game tree; must stay green).
2. A fix starts with a failing test in `tests/test_cpforge.py`.
3. Against a real install: `cpforge doctor`, `cpforge index`, then
   `cpforge new T --kind <each>` + `cpforge check --compile` in a temp folder.
4. Update `CHANGELOG.md`, `STATE.md`, and bump `__version__` together.

## Boundaries

- Game folder, mod-manager staging, saves and other tools are read-only
  inputs. Writes: the project, the forge home, and the game only via `deploy`.
- No downloads of mods or tools, no uploads, no game launch.
- Never commit game files or anything extracted from them (tests use synthetic
  fixtures).
- Paths with spaces, `!`, parentheses: pass argv lists, never shell strings.
- Batch/PowerShell files CRLF, everything else LF (`.gitattributes`).
- Evidence tiers stay separate: static, compile, package, load, gameplay.
