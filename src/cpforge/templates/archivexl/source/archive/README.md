# {{NAME}} archive resources

Put the resource tree from your WolvenKit project here, at the same paths the
game uses. For this template:

```
{{ID_LOWER}}\factories\{{ID_LOWER}}.csv
{{ID_LOWER}}\localization\en-us.json
{{ID_LOWER}}\...  (.ent, .app, .mesh, textures)
```

Then `cpforge build` packs this folder into `game/archive/pc/mod/{{ID}}.archive`
with the WolvenKit CLI (set `WOLVENKIT_CLI` to `WolvenKit.CLI.exe` if it is not
on PATH), and `cpforge check` confirms the paths in `{{ID}}.archive.xl` are in
the archive. This README is not packed into the release.
