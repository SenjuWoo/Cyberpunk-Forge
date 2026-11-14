# WolvenKit

The resource editor for Cyberpunk 2077 (meshes, textures, entities,
appearances, archives). The forge does not replace it; it drives the CLI for
the repeatable parts and checks the results.

- GUI: create the project, edit resources, preview.
- CLI (`WolvenKit.CLI.exe`, tool name `cp77tools`): `pack <folder> -o <out>`
  builds an `.archive`; `unbundle`/`uncook` extract from game archives;
  `export`/`import` convert raw files; `hash` prints FNV-1a hashes.
- The forge finds it through `WOLVENKIT_CLI=<path to WolvenKit.CLI.exe>`, PATH,
  the dotnet tools folder, or the Reverse THIS! kit folder. `cpforge doctor`
  shows which path it uses.
- Vehicle work (mesh import onto vanilla templates, tangent sign, material
  JSON): see `cpforge knowledge vehicles`.
- Releases: https://github.com/WolvenKit/WolvenKit/releases

Keep extracted game files out of public repositories; ship only your own
resources.
