# Nexus Mods release

`cpforge nexus` writes `dist/nexus/<version>/`:

- `description.bbcode` - name, summary, what's new (from CHANGELOG.md),
  requirements with links (from `requires` in `cpforge.json`), install note
- `changelog.txt` - one block per version for the Nexus changelog tab
- `file-description.txt`, `summary.txt`

It flags machine paths that would leak into public text. It never uploads:
you paste and upload.

Checklist:
- version in `cpforge.json`, CHANGELOG.md and any version file agree
  (`cpforge check` enforces the mirrors listed in `version_files`)
- requirements list every framework the mod needs, with minimum versions
- the zip passed `cpforge validate`
- screenshots or a short clip of the feature working in game
- the file description says what changed and how to update (delete the old
  folder first when files were renamed)
