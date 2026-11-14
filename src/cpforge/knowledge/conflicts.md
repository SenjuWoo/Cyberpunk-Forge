# Conflicts

`cpforge conflicts [--what scripts|archives|tweaks]`

- **scripts** (from the index; rerun `cpforge index` after changing mods):
  two mods `@replaceMethod` on the same method (only one survives), the same
  member added twice (compile error), and the most-wrapped methods (wraps
  stack, but heavy wrapping is where load-order surprises live).
- **archives**: every `.archive` in `archive/pc/mod` and REDmod `archives/`
  folders is read; pairs that ship the same resource hash are listed with
  counts. Many overlaps are intended (compatibility patches). Names appear only
  when an archive embeds an uncompressed name list.
- **tweaks**: fields that different mods set to different plain values (one
  wins by load order). Records only extended with array tags (`!append`, or
  `- !append x` list items) by several mods are normal and only counted.

Fixing one: ask both authors for a compatibility patch, pick one mod, or write
a patch mod that wraps instead of replacing.
