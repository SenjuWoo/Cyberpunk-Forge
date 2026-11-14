# Updating a mod for a new game patch

1. `cpforge doctor` - confirms the game version and that the frameworks are
   current for it.
2. `cpforge index` - rebuild the API/TweakDB index for the new version (the
   index is stored per game version, so old and new can be compared).
3. `cpforge check --compile` in the mod project:
   - static check flags hook targets (`@wrapMethod(Class)` method) that no longer
     exist and suggests close names
   - the compile shows signature changes (`UNRESOLVED_*`, argument mismatches)
4. `cpforge tweak exists` for every record the mod references; TweakDB records
   are renamed or removed between patches too.
5. RED4ext plugins: rebuild against an SDK that declares the new runtime.
6. Test in game, then `cpforge logs --mod <Name>`.
7. `cpforge bump minor`, write the changelog, `cpforge package`, `cpforge nexus`.

Keep the previous release zip (`bump` copies it to `dist/known-good/`) so users
on the old patch still have a working file.
