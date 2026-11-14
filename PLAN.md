# Plan

## Next

- Opt-in MCP server exposing the same commands (stdio, started by the user's
  agent only when needed).
- RED .tweak syntax check (TweakXL `.tweak` files).
- Static check for calls to native-only functions (the `LogChannel` trap)
  before compiling.
- `cpforge api diff <old-version> <new-version>`: what a game patch removed or
  changed, from two stored indexes.
- WolvenKit CLI integration beyond `pack`: unbundle a resource for reference,
  convert to/from JSON for diffable edits.
- Phantom Liberty / Dogtown helpers (district and fast-travel data from the
  install).
- Install/update run twice in CI; release workflow with checksums.

## Not planned

- Downloading mods, frameworks or game files.
- Uploading to Nexus (the forge writes the kit; publishing stays manual).
