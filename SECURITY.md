# Security

Report a vulnerability through GitHub's private vulnerability reporting on this
repository (Security tab), not in a public issue.

What the forge does and does not do:

- Reads the game folder, mod logs and mod files; writes only to your project,
  to `%LOCALAPPDATA%\CyberpunkForge` (index, logs, build dependencies), and to
  the game folder when you run `cpforge deploy` (with a receipt and backups).
- Runs external programs only when you ask: the game's `scc.exe` (compile),
  CMake/MSVC (build), the WolvenKit CLI (pack, convert for `res`), luajit/luac
  (syntax check). Every run has a timeout; a stopped run ends only its own
  process.
- `deploy` replaces game files by rename, so a file a mod manager hard-linked
  from its staging folder is never changed in staging.
- Makes no network requests itself. `cpforge build` lets CMake fetch
  RED4ext.SDK from GitHub at a pinned commit.
- Scans packages for common API-key formats so you do not publish one by
  accident. It never prints a full key.
