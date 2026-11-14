# WolvenKit

The resource editor for Cyberpunk 2077 (meshes, textures, entities,
appearances, archives). The forge does not replace it; it drives the CLI for
the repeatable parts and checks the results.

- GUI: create the project, edit resources, preview.
- CLI (`WolvenKit.CLI.exe`, tool name `cp77tools`): `pack <folder> -o <out>`
  builds an `.archive`; `unbundle`/`uncook` extract from game archives;
  `export`/`import` convert raw files; `hash` prints FNV-1a hashes.
- Point the forge at it with `WOLVENKIT_CLI=<path to WolvenKit.CLI.exe>` or put
  it on PATH. `cpforge doctor` shows whether it was found.
- Releases: https://github.com/WolvenKit/WolvenKit/releases

Keep extracted game files out of public repositories; ship only your own
resources.
