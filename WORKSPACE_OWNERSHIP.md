# Workspace ownership

- Project root: `.` (this file's directory; one owner shared by every agent).
- Active source: `src/cpforge/` (package, knowledge data, templates), `skills/`, `tests/`.
- Versioning: Git on `main`, tags `vX.Y.Z`; the version lives in `src/cpforge/__init__.py`.
- Repository: public GitHub repository `Cyberpunk-Forge` (MIT), requested by the owner.
- Publication intent: the repository is public; releases are cut from a tag after CI passes on that commit.
- Explicit GitHub publication: public and MIT for original work by default, subject to rights/platform terms; preserve existing licences. Generic publication uses the appropriate destination (Nexus for Skyrim); do not create duplicate source hosting for mods needing no compilation.
- Existing-repository maintenance: preserve its remote/visibility and follow the requested update, documentation, push and release scope.
- Read-only inputs: installed products, game Data/staging/saves and supplied references.
- Release staging: separate runtime payload from source, ownership notes, STATE/PLAN/validation, changelogs, logs and backups. Keep required licences.
- Recovery: read STATE.md and version/build/run metadata before continuing; keep the last known-good artifact.


Read the existing evidence and update the active-source/version fields before substantive edits. Do not create another owner or move files merely to match a template.
