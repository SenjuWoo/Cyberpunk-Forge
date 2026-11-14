# Plan

## Next

- Opt-in MCP server exposing the same commands (stdio, started by the user's
  agent only when needed).
- WolvenKit CLI integration beyond `pack` and `convert` (used by `res`):
  `cpforge res extract <vanilla path>` to unbundle a reference resource.
- Phantom Liberty / Dogtown helpers (district and fast-travel data from the
  install).
- Vehicles: after the car's in-game test, record what held and what broke in
  `vehicles.md`; then a `vehicle` template (base-car copy + record + listing),
  and the car project's generic tools as commands: glb reader/writer with the
  WolvenKit tangent sign, rig editor that keeps bone order, handle re-id and
  compiledData rebuild for `.app`, `.phys` affine fit, light placement from
  vertex-colour zones.
- `res check`: light zones per light submesh (needs the vertex colours from the
  mesh buffer, not in the JSON).
- Field-type check for `.tweak` and YAML values against the record schema.

## Not planned

- Downloading mods, frameworks or game files.
- Uploading to Nexus (the forge writes the kit; publishing stays manual).
