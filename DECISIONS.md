# Decisions

- **CLI first, JSON always.** Agents parse; people read the same JSON or the
  README. An MCP server may come later as an opt-in wrapper; nothing needs a
  running server.
- **Installed game over documentation.** The index is built from the user's
  own REDmod sources, `metadata.json` and installed `.reds`. File formats in
  `facts.json` were confirmed by running the readers against a 2.5 install
  (archive index sizes, 39/39 ArchiveXL factory hashes, TweakDB IDs and type
  keys).
- **No game data in the repository.** Tests build a fake game tree.
- **RED4ext.SDK pinned to commit 0f5eba4**, not tag 1.0.0: the tag declares 2.31
  as the latest runtime and RED4ext refuses such a plugin on 2.5. Move the pin
  only after a CI build.
- **Fetched build dependencies live in the forge home** (short path): the SDK's
  generated headers exceed MAX_PATH under deep project folders and git skips
  them silently.
- **Compile with dependencies only.** The standalone `scc.exe` can overflow its
  stack on a full large load order; `script_dependencies` in `cpforge.json`
  lists the r6/scripts folders a mod needs. Plugin-shipped `.reds` are always
  passed via `-compilePathsFile`.
- **Templates log with `FTLog`.** `LogChannel` is native-only in vanilla and
  fails to compile without a logging-headers mod.
- **Deploy is explicit and reversible.** Receipt with hashes, backups of
  anything overwritten, undeploy removes only files still matching their hash.
- **.tweak checks are structural, calibrated on the real corpus.** The parser
  must read every vanilla `.tweak` file without a finding before a rule ships;
  base and reference misses are warnings because resolution (package, `using`,
  record types) is inferred, not documented.
- **Native-only calls are judged by declaration origin.** A global is flagged
  only when metadata.json lists it and no vanilla script declares it; redscript
  intrinsics and mod-defined script functions are never flagged.
- **Releases come from tags on green commits.** The Release workflow checks the
  tag against `__version__` and CHANGELOG and requires a successful CI run on
  that SHA before it publishes.
- **Deterministic packages.** Sorted entries, fixed timestamps, forward
  slashes; the same input gives the same bytes.
