# Security

Report a vulnerability through GitHub's private vulnerability reporting on this
repository (Security tab), not in a public issue.

What the forge does and does not do:

- Reads the game folder, mod logs and mod files; writes only to your project,
  to `%LOCALAPPDATA%\CyberpunkForge` (index, logs, build dependencies), and to
  the game folder when you run `cpforge deploy` (with a receipt and backups).
- Runs external programs only when you ask: the game's `scc.exe` (compile),
  CMake/MSVC (build), the WolvenKit CLI (pack), luajit/luac (syntax check).
- Makes no network requests itself. `cpforge build` lets CMake fetch
  RED4ext.SDK from GitHub at a pinned commit.
- Scans packages for common API-key formats so you do not publish one by
  accident. It never prints a full key.
