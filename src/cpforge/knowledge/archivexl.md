# ArchiveXL (new resources)

An `.archive` in `archive/pc/mod/` holds resources (meshes, textures, `.ent`,
`.app`, factory `.csv`, localization `.json`). ArchiveXL reads
`<name>.archive.xl` next to it to register those resources with the game.

## Keys seen in use

- `factories:` list of `.csv` resource paths (entity factories for new items)
- `localization: onscreens: { en-us: <path>.json }` UI strings
- `streaming: blocks / sectors` world sector edits (observed in installed mods)
- `player: bodyTypes:` body type registration

Paths are resource paths inside the archive, backslash-separated, no quotes
needed. Resource hashes are FNV-1a 64 of the lowercase path.

## New item recipe

1. Make the resources in WolvenKit; keep the resource tree under
   `source/archive/` in the forge project.
2. `cpforge build` packs it with the WolvenKit CLI into
   `game/archive/pc/mod/<Mod>.archive`.
3. Register the factory and strings in `<Mod>.archive.xl`.
4. Add the item record in `r6/tweaks/<Mod>/` (`$base: Items.GenericFaceClothing`
   or another real base; `entityName` = factory row, `appearanceName` = appearance
   prefix, `displayName` = localization secondaryKey).
5. `cpforge check` confirms every `.xl` path is really inside the archive.

## Useful commands

- `cpforge archive info <file.archive>` - entry counts, embedded names
- `cpforge archive find <resource path> --vanilla` - which archives contain it
- `cpforge hash <resource path>` - the 64-bit hash
- `cpforge conflicts --what archives` - mods shipping the same resource
