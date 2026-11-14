# Plan

## Next

- Opt-in MCP server exposing the same commands (stdio, started by the user's
  agent only when needed).
- WolvenKit CLI integration beyond `pack`: unbundle a resource for reference,
  convert to/from JSON for diffable edits.
- Phantom Liberty / Dogtown helpers (district and fast-travel data from the
  install).
- Vehicles: finish `vehicles.md` (ent/app, light components, shadow and proxy
  meshes, burnt appearance, TweakXL record, VCD listing) from the car-mod
  project; then a `vehicle` template and checks (record fields, ent/app paths
  inside the archive, light zones per light submesh), and that project's
  generic tools (glb tangent fix, rig pivot writer) as commands.
- Field-type check for `.tweak` and YAML values against the record schema.

## Not planned

- Downloading mods, frameworks or game files.
- Uploading to Nexus (the forge writes the kit; publishing stays manual).
